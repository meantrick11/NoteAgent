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

from NoteAgent.BusinessModules.ChatAgent.ChatExecution import execute_turn
from NoteAgent.BusinessModules.ChatAgent.ChatGraph import build_chat_graph
from NoteAgent.BusinessModules.ChatAgent.ChatNodes import GraphRuntime
from NoteAgent.BusinessModules.ConversationState.ConversationCheckpoints import CheckpointRuntime, checkpoint_id_of
from NoteAgent.BusinessModules.ConversationState.ConversationContracts import PreparedTurn, DraftApproval
from NoteAgent.BusinessModules.ConversationState.ConversationStateService import ConversationService

_logger = logging.getLogger(__name__)

# Draft action -> mutation kind; append/replace differ only by the append flag.


class ChatAgent:
    """One chat profile's graph runtime plus the shared checkpoint service."""

    def __init__(self, *, runtime: GraphRuntime, service: ConversationService,
                 checkpoints: CheckpointRuntime, approvals: DraftApproval) -> None:
        """Bind graph execution and the shared conversation/review interfaces."""
        self._runtime = runtime
        self._service = service
        self._checkpoints = checkpoints
        self._approvals = approvals

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

    def claim_prepared(self, run_id: str, **kwargs) -> PreparedTurn:
        """Claim a prepared (recovery-forked) run without re-accepting its message."""
        return self._service.claim_prepared(run_id, **kwargs)

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


    async def update_draft_content(self, conversation_id: str, content: str, *,
                                   expected_revision: int | None = None,
                                   file_name: str | None = None) -> dict:
        """Delegate draft edits to the injected review workflow."""
        return await self._approvals.update_draft_content(
            conversation_id, content, expected_revision=expected_revision, file_name=file_name,
        )

    async def review(self, conversation_id: str, action: str,
                     write_action: str | None = None, file_name: str | None = None, *,
                     expected_revision: int | None = None) -> dict:
        """Delegate human review while keeping the existing Agent call interface."""
        return await self._approvals.review(
            conversation_id, action, write_action=write_action, file_name=file_name,
            expected_revision=expected_revision,
        )
