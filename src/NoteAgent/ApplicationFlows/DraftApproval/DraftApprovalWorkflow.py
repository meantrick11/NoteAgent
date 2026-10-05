"""Human draft review: coordinate conversation state, durable notes and indexing."""

from __future__ import annotations
from NoteAgent.BusinessModules.ConversationState.PendingDrafts import WRITE_ACTIONS, DraftStore, markdown_name
from NoteAgent.BusinessModules.ConversationState.LegacyConversationCompatibility.LegacyDraftReview import commit_review, _sync_index, _write_draft
from NoteAgent.BusinessModules.ConversationState.ConversationStateService import ConversationService
from NoteAgent.BusinessModules.NoteStorage.NoteChanges import CREATE, DELETE, WRITE, MutationCommand, MutationError, Origin
from NoteAgent.BusinessModules.NoteStorage.MarkdownRepository import FileNoteRepository
from NoteAgent.BusinessModules.NoteRetrieval.NoteRetrievalService import RetrievalService

_DRAFT_KINDS = {"create": CREATE, "append": WRITE, "replace": WRITE, "delete": DELETE}


class DraftApprovalWorkflow:
    """Keep note writes and draft-state publication under the existing recovery protocol."""

    def __init__(self, *, service: ConversationService, notes: FileNoteRepository,
                 legacy_drafts: DraftStore, retrieval: RetrievalService | None = None,
                 mutations=None) -> None:
        self._service = service
        self._notes = notes
        self._legacy_drafts = legacy_drafts
        self._retrieval = retrieval
        self._mutations = mutations

    def _is_checkpoint(self, conversation_id: str) -> bool:
        record = self._service.get(conversation_id)
        return bool(record is not None and record.state_backend == "checkpoint")


    async def update_draft_content(
        self, conversation_id: str, content: str, *, expected_revision: int | None = None,
        file_name: str | None = None,
    ) -> dict:
        """Save edits to the pending draft. Only the conversation state changes."""
        if self._is_checkpoint(conversation_id):
            draft = await self._service.update_pending_draft(
                conversation_id, content, expected_revision=expected_revision,
                file_name=self._notes.normalize(file_name) if file_name is not None else None,
            )
            if draft is None:
                return {"error": "no pending draft"}
            return {"status": "updated", "pending_draft": draft}
        if file_name is not None:
            raise ValueError("migrate the conversation before renaming a draft")
        draft = self._legacy_drafts.update_content(conversation_id, content)
        if draft is None:
            return {"error": "no pending draft"}
        return {"status": "updated", "pending_draft": draft.as_dict()}


    async def review(
        self,
        conversation_id: str,
        action: str,
        write_action: str | None = None,
        file_name: str | None = None,
        *,
        expected_revision: int | None = None,
    ) -> dict:
        """Approve, override, or reject the pending draft for this conversation."""
        if not self._is_checkpoint(conversation_id):
            return commit_review(
                self._notes,
                self._legacy_drafts,
                conversation_id,
                action,
                write_action=write_action,
                file_name=file_name,
                retrieval=self._retrieval,
            )

        applied_operation = None

        def apply(draft: dict) -> dict:
            nonlocal applied_operation
            if action == "reject":
                return {"status": "rejected"}
            if action == "override":
                if write_action not in WRITE_ACTIONS or not file_name:
                    return {"error": "override requires write_action and file_name"}
                target_action, target_name = write_action, markdown_name(file_name)
            elif action == "approve":
                target_action, target_name = draft.get("action"), draft.get("file_name")
            else:
                return {"error": f"unknown action {action}"}
            try:
                mutation = self._write_approved(
                    conversation_id, target_action, target_name,
                    draft.get("content") or "", draft["_head_id"], branch_id=draft["_branch_id"],
                )
            except (OSError, ValueError, MutationError) as exc:
                return {"error": str(exc)}
            payload = {"status": "written", "action": target_action, "file_name": target_name}
            if mutation is not None:
                applied_operation = mutation.operation_id
                payload.update(_mutation_operation=mutation.operation_id, notes_commit=mutation.commit, workspace_seq=mutation.workspace_seq)
            return payload

        try:
            return await self._service.review_pending_draft(
                conversation_id, apply, expected_revision=expected_revision,
                allow_absent=action == "reject",
            )
        except Exception:
            if applied_operation:
                self._mutations.retain_approval(applied_operation)
            raise


    def _write_approved(self, conversation_id, action, file_name, content,
                        expected_revision, *, branch_id=None):
        """Write an approved draft through the unified mutation service when present.

        The mutation service records the operation and its before-bytes, commits the
        shadow Git version and updates the index; without it (test/diagnostic
        containers) the legacy direct write path is used.
        """
        if self._mutations is None:
            _write_draft(self._notes, action, file_name, content)
            _sync_index(self._retrieval, action, file_name)
            return
        kind = _DRAFT_KINDS.get(action)
        if kind is None:
            raise ValueError(f"unknown write action {action}")
        command = MutationCommand(
            kind=kind,
            file_name=file_name,
            content=content,
            title=file_name.rsplit("/", 1)[-1].removesuffix(".md"),
            append=action != "replace",
        )
        origin = Origin(
            kind="conversation",
            conversation_id=conversation_id,
            branch_id=branch_id,
            run_id=f"draft-{expected_revision}",
        )
        return self._mutations.apply(
            command, origin, f"draft-{conversation_id}-{expected_revision}",
            retrieval=self._retrieval,
        )
