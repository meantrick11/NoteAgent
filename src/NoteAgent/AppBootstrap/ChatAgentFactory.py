"""Build a graph-backed ChatAgent outside the HTTP container.

The eval harnesses and integration tests need the same prepare/execute contract as
production without the FastAPI container. They still use a real ConversationService
over an isolated checkpointer (in-process for tests, sqlite/postgres for harnesses),
so nothing here bypasses the turn protocol.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Awaitable, Sequence
from datetime import datetime, timezone

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import InMemorySaver

from NoteAgent.BusinessModules.ChatAgent.ChatAgent import ChatAgent
from NoteAgent.ApplicationFlows.DraftApproval.DraftApprovalWorkflow import DraftApprovalWorkflow
from NoteAgent.BusinessModules.ChatAgent.ConversationContext.ContextBudget import ContextBudget
from NoteAgent.BusinessModules.ConversationState.PendingDrafts import DraftStore
from NoteAgent.BusinessModules.ChatAgent.ChatEvents import chunk_text
from NoteAgent.BusinessModules.ChatAgent.ChatNodes import GraphRuntime
from NoteAgent.BusinessModules.ConversationState.ConversationCheckpoints import CheckpointRuntime, checkpoint_id_of
from NoteAgent.BusinessModules.ConversationState.ConversationRecords import MessageRecord, message_dict_from_record
from NoteAgent.BusinessModules.ConversationState.ConversationStateService import ConversationService
from NoteAgent.BusinessModules.NoteStorage.MarkdownRepository import FileNoteRepository
from NoteAgent.BusinessModules.NoteRetrieval.NoteRetrievalService import RetrievalService


def local_checkpoints() -> CheckpointRuntime:
    """An in-process checkpointer for isolated runs; never the production store."""
    return CheckpointRuntime.attached(InMemorySaver())


def model_summarizer(
    model: BaseChatModel,
) -> Callable[[str | None, str], Awaitable[str]]:
    """Drop the oldest turns into a fresh summary chunk using the given model."""

    async def summarize(old: str | None, dropped: str) -> str:
        prompt = (
            "下面「已有摘要」不要改写。"
            "只摘要「移出窗口的对话」，保住用户任务目标。"
            "只输出新摘要段落。\n\n"
            f"已有摘要：\n{old or '（空）'}\n\n移出的对话：\n{dropped}"
        )
        result = await model.ainvoke([HumanMessage(content=prompt)])
        return chunk_text(result.content)

    return summarize


def build_graph_agent(
    *,
    model: BaseChatModel,
    tools: list[BaseTool],
    notes: FileNoteRepository,
    drafts: DraftStore,
    budget: ContextBudget,
    system_prompt: str,
    service: ConversationService,
    checkpoints: CheckpointRuntime,
    retrieval: RetrievalService | None = None,
    mutations=None,
) -> ChatAgent:
    """Assemble a ChatAgent over an explicit service and checkpointer."""
    runtime = GraphRuntime(
        model=model,
        tools=tools,
        drafts=drafts,
        budget=budget,
        system_prompt=system_prompt,
        summarize_dropped=model_summarizer(model),
        retrieval=retrieval,
    )
    return ChatAgent(
        runtime=runtime,
        service=service,
        checkpoints=checkpoints,
        approvals=DraftApprovalWorkflow(
            service=service, notes=notes, legacy_drafts=drafts,
            retrieval=retrieval, mutations=mutations,
        ),
    )


async def seed_dialogue(
    service: ConversationService,
    conversation_id: str,
    pairs: Sequence[tuple[str, str]],
) -> None:
    """Write existing user/assistant turns into the active head without a model call.

    Used by eval harnesses to establish short-memory context before the scored turn.
    Each two adjacent entries become one turn so compaction sees complete turns.
    """
    view = await service.get_state(conversation_id)
    values = dict(view.values)
    ui = list(values.get("ui_messages") or [])
    for index in range(0, len(pairs), 2):
        turn_id = str(uuid.uuid4())
        for role, content in pairs[index : index + 2]:
            ui.append(
                message_dict_from_record(
                    MessageRecord(
                        id=str(uuid.uuid4()),
                        conversation_id=conversation_id,
                        role=role,
                        content=content,
                        created_at=datetime.now(timezone.utc),
                        turn_id=turn_id,
                        tool_name=None,
                        tool_arguments=None,
                        output_preview=None,
                        truncated=False,
                        status=None,
                    )
                )
            )
    values["ui_messages"] = ui
    values["working_records"] = list(ui)
    branch_id = str(values.get("branch_id") or service.active_branch_id(conversation_id))
    await service.write_state(
        conversation_id,
        values,
        branch_id=branch_id,
        parent_checkpoint_id=checkpoint_id_of(view.config),
        publish=True,
    )


async def conversation_tool_steps(
    service: ConversationService, conversation_id: str
) -> list[dict]:
    """Every tool step attached to an assistant bubble, in turn order."""
    records = await service.list_messages(conversation_id) or []
    steps: list[dict] = []
    for record in records:
        if record.role != "assistant":
            continue
        steps.extend(record.tool_steps or [])
    return steps
