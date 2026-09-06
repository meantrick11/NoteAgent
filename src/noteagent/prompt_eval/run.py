"""Run one golden-set case through an in-process ChatAgent. Never commit_review."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from noteagent.bootstrap.settings import Settings
from noteagent.chat.agent import ChatAgent
from noteagent.chat.context_budget import budget_from_settings
from noteagent.chat.drafts import DraftStore
from noteagent.chat.history import ConversationStore, start_turn
from noteagent.chat.tools import build_chat_tools
from noteagent.db import Base, create_engine_from_url, create_session_factory
from noteagent.notes.repository import FileNoteRepository
from noteagent.prompt_eval.cases import EvalCase
from noteagent.prompt_eval.report import case_filename, write_stage
from noteagent.prompt_eval.score import RUBRIC_VERSION, score_note

_logger = logging.getLogger(__name__)


@dataclass
class ToolHop:
    """One tool stub collected from conversation history after the turn."""

    name: str
    arguments: str
    output_preview: str
    status: str | None


@dataclass
class CaseRun:
    """One scored case plus the traces written into n05.md / b06.md."""

    seq: int
    case: EvalCase
    score: object
    tools: list[ToolHop] = field(default_factory=list)
    draft: dict | None = None
    assistant_final: str | None = None
    error: str | None = None


class _FakeRetrieval:
    """b04 only checks that search was called; skip MiniLM and real Chroma."""

    def search(self, query: str, top_k: int = 3):
        _logger.info("eval fake search query=%.80s top_k=%s", query, top_k)
        return []


def build_eval_agent(
    notes_root: Path,
    *,
    model,
    prompt_path: Path,
    settings: Settings,
) -> tuple[ChatAgent, FileNoteRepository, ConversationStore, DraftStore]:
    """Temp notes + sqlite memory + fake retriever. Same four tools as production."""
    notes = FileNoteRepository(notes_root)
    engine = create_engine_from_url("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    history = ConversationStore(create_session_factory(engine))
    drafts = DraftStore()
    tools = build_chat_tools(notes, _FakeRetrieval(), drafts)
    agent = ChatAgent(
        model=model,
        tools=tools,
        notes=notes,
        drafts=drafts,
        history=history,
        budget=budget_from_settings(settings),
        prompt_path=prompt_path,
    )
    return agent, notes, history, drafts


def seed_notes(notes: FileNoteRepository, seed_files: dict[str, str]) -> None:
    """Write short fixture notes so behavior cases do not need the user's notes/."""
    for name, body in seed_files.items():
        rel = notes.create(name, Path(name).stem)
        notes.write(rel, body, append=False)
        _logger.info("eval seed file=%s chars=%d", rel, len(body))


async def run_case(
    case: EvalCase,
    *,
    seq: int,
    agent: ChatAgent,
    notes: FileNoteRepository,
    history: ConversationStore,
    drafts: DraftStore,
) -> CaseRun:
    """One user turn: seed files, stream, collect tools/draft, score. No review."""
    _logger.info("eval case start id=%s seq=%02d", case.id, seq)
    seed_notes(notes, case.seed_files)
    record = history.create(case.id)
    turn_id = start_turn()
    history.append_message(record.id, "user", case.user, turn_id=turn_id)
    assistant_final: str | None = None
    error: str | None = None
    try:
        async for item in agent.stream(case.user, thread_id=record.id, turn_id=turn_id):
            if item.get("event") == "assistant_final" and isinstance(item.get("data"), str):
                assistant_final = item["data"]
    except Exception as exc:
        error = str(exc)
        _logger.exception("eval case failed id=%s", case.id)
    pending = drafts.get(record.id)
    draft = pending.as_dict() if pending is not None else None
    tools = _collect_tools(history, record.id)
    score = score_note(
        case,
        proposed=draft is not None,
        tools=[hop.name for hop in tools],
        action=None if draft is None else draft.get("action"),
        file_name=None if draft is None else draft.get("file_name"),
        content=None if draft is None else draft.get("content"),
    )
    _logger.info(
        "eval case end id=%s propose=%s tools=%s behavior_pass=%s total=%s",
        case.id,
        draft is not None,
        [hop.name for hop in tools],
        score.behavior_pass,
        score.total,
    )
    return CaseRun(
        seq=seq,
        case=case,
        score=score,
        tools=tools,
        draft=draft,
        assistant_final=assistant_final,
        error=error,
    )


async def run_eval(
    cases: list[EvalCase],
    *,
    dest: Path,
    prompt_path: Path,
    settings: Settings,
    model,
    prompt_display: str,
    cases_display: str,
    case_filter: list[str] | None = None,
    label: str | None = None,
) -> list[CaseRun]:
    """Run every case with a fresh temp notes dir. Reuse the same chat model."""
    started = datetime.now(timezone.utc)
    prompt_text = prompt_path.read_text(encoding="utf-8")
    prompt_sha = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()
    runs: list[CaseRun] = []
    for seq, case in enumerate(cases, start=1):
        with TemporaryDirectory(prefix=f"noteagent-eval-{case.id}-") as tmp:
            agent, notes, history, drafts = build_eval_agent(
                Path(tmp) / "notes",
                model=model,
                prompt_path=prompt_path,
                settings=settings,
            )
            run = await run_case(
                case, seq=seq, agent=agent, notes=notes, history=history, drafts=drafts
            )
            runs.append(run)
    finished = datetime.now(timezone.utc)
    config = {
        "rubric_version": RUBRIC_VERSION,
        "chat_model": settings.chat_model,
        "prompt_sha256": prompt_sha,
        "prompt_path": prompt_display,
        "cases_path": cases_display,
        "case_filter": case_filter,
        "label": label,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "case_ids": {run.case.id: case_filename(run.case.id) for run in runs},
    }
    write_stage(dest, prompt_text=prompt_text, config=config, runs=runs)
    return runs


def _collect_tools(history: ConversationStore, conversation_id: str) -> list[ToolHop]:
    """Tool stubs in created_at order. Names are the behavior-gate sequence.

    ``list_messages`` is UI-only (user/assistant). Stubs live as role=tool rows
    and are returned by ``list_persistent_after_watermark``.
    """
    messages = history.list_persistent_after_watermark(conversation_id)
    hops: list[ToolHop] = []
    for record in messages:
        if record.role != "tool" or not record.tool_name:
            continue
        hops.append(
            ToolHop(
                name=record.tool_name,
                arguments=record.tool_arguments or "",
                output_preview=record.output_preview or "",
                status=record.status,
            )
        )
    return hops
