"""Graph-backed chat facade.

The production agent no longer owns a hand-written tool loop: it prepares a turn
through :class:`ConversationService` (which durably accepts the user message), runs
the compiled LangGraph over the shared checkpointer, and publishes the active head
through the service's CAS. Draft edits and reviews branch on the conversation's
backend so un-migrated histories keep the legacy behaviour until A1 imports them.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from noteagent.chat.drafts import (
    WRITE_ACTIONS,
    DraftStore,
    commit_review,
    markdown_name,
    _sync_index,
    _write_draft,
)
from noteagent.chat.execution import execute_turn
from noteagent.chat.graph import build_chat_graph
from noteagent.chat.nodes import GraphRuntime
from noteagent.conversations.checkpoints import CheckpointRuntime, checkpoint_id_of
from noteagent.conversations.contracts import PreparedTurn
from noteagent.conversations.service import ConversationService
from noteagent.notes.mutations import (
    CREATE,
    DELETE,
    WRITE,
    MutationCommand,
    MutationError,
    Origin,
)
from noteagent.notes.repository import FileNoteRepository
from noteagent.retrieval.service import RetrievalService

_logger = logging.getLogger(__name__)

# Draft action -> mutation kind; append/replace differ only by the append flag.
_DRAFT_KINDS = {"create": CREATE, "append": WRITE, "replace": WRITE, "delete": DELETE}


class ChatAgent:
    """One chat profile's graph runtime plus the shared checkpoint service."""

    def __init__(
        self,
        *,
        runtime: GraphRuntime,
        service: ConversationService,
        checkpoints: CheckpointRuntime,
        notes: FileNoteRepository,
        legacy_drafts: DraftStore,
        retrieval: RetrievalService | None = None,
        mutations=None,
    ) -> None:
        self._runtime = runtime
        self._service = service
        self._checkpoints = checkpoints
        self._notes = notes
        self._legacy_drafts = legacy_drafts
        self._retrieval = retrieval
        self._mutations = mutations

    # ---- turn execution ---------------------------------------------------

    async def prepare(
        self, conversation_id: str, question: str, request_id: str,
        *, expected_revision: int | None = None,
    ) -> PreparedTurn:
        """Claim the turn and durably accept the user message before streaming."""
        return await self._service.prepare_turn(
            conversation_id, question, request_id, expected_revision=expected_revision
        )

    def resume(self, run_id: str, *, conversation_id: str | None = None,
               expected_revision: int | None = None) -> PreparedTurn:
        """Explicitly claim an interrupted run; the user message is not re-accepted."""
        return self._service.resume_turn(
            run_id, conversation_id=conversation_id, expected_revision=expected_revision,
        )

    def claim_prepared(self, run_id: str) -> PreparedTurn:
        """Claim a prepared (recovery-forked) run without re-accepting its message."""
        return self._service.claim_prepared(run_id)

    async def run(self, prepared: PreparedTurn, *, resume: bool = False) -> AsyncIterator[dict]:
        """Run the compiled graph for an already-prepared turn and emit its events."""
        graph = build_chat_graph(self._runtime, self._checkpoints.saver)
        async for event in execute_turn(graph, self._service, prepared, resume=resume):
            yield event
        state = await self._service.get_state(prepared.conversation_id)
        yield {
            "event": "turn_complete",
            "data": {
                "run_id": prepared.run_id,
                "turn_id": prepared.turn_id,
                "status": state.values.get("run_status"),
                "checkpoint_id": checkpoint_id_of(state.config),
                # The conversation's head revision after this publish: the token the
                # next draft edit/approval must send back.
                "state_revision": self._service.current_revision(prepared.conversation_id),
            },
        }

    async def stream(
        self, question: str, conversation_id: str, *, request_id: str,
        expected_revision: int | None = None,
    ) -> AsyncIterator[dict]:
        """Prepare and run one turn; the convenience path used by eval harnesses."""
        prepared = await self.prepare(
            conversation_id, question, request_id, expected_revision=expected_revision
        )
        yield {
            "event": "user_message",
            "data": {
                "message_id": prepared.user_message_id,
                "turn_id": prepared.turn_id,
                "run_id": prepared.run_id,
                "request_id": prepared.request_id,
                "state_revision": prepared.generation,
            },
        }
        async for event in self.run(prepared):
            yield event

    # ---- drafts -----------------------------------------------------------

    def _is_checkpoint(self, conversation_id: str) -> bool:
        record = self._service.get(conversation_id)
        return bool(record is not None and record.state_backend == "checkpoint")

    async def update_draft_content(
        self, conversation_id: str, content: str, *, expected_revision: int | None = None
    ) -> dict:
        """Save edits to the pending draft. Only the conversation state changes."""
        if self._is_checkpoint(conversation_id):
            draft = await self._service.update_pending_draft(
                conversation_id, content, expected_revision=expected_revision
            )
            if draft is None:
                return {"error": "no pending draft"}
            return {"status": "updated", "pending_draft": draft}
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

        def apply(draft: dict) -> dict:
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
                self._write_approved(
                    conversation_id, target_action, target_name,
                    draft.get("content") or "", expected_revision,
                )
            except (OSError, ValueError, MutationError) as exc:
                return {"error": str(exc)}
            return {"status": "written", "action": target_action, "file_name": target_name}

        result = await self._service.review_pending_draft(
            conversation_id, apply, expected_revision=expected_revision,
            allow_absent=action == "reject",
        )
        return result

    def _write_approved(self, conversation_id, action, file_name, content,
                        expected_revision) -> None:
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
            run_id=f"draft-{expected_revision}",
        )
        self._mutations.apply(
            command, origin, f"draft-{conversation_id}-{expected_revision}",
            retrieval=self._retrieval,
        )
