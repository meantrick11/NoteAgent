"""Deterministic doubles shared by checkpoint/recovery tests."""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Iterable

# 恢复/写入流程中可注入故障的阶段；顺序与 §5.5 的持久阶段一致。
FAULT_STAGES = (
    "file_applied",
    "git_committed",
    "index_rebuilt",
    "candidate_saved",
    "before_publish",
    "after_publish",
)


class FailInjector:
    """Raise a registered exception once at a named stage, then stop injecting.

    Production code takes one of these (or an equivalent hook) as a dependency and
    calls :meth:`check` at each persisted stage boundary. Tests register faults so
    the same stage fails exactly once, which is what the restart-and-retry cases
    depend on.
    """

    def __init__(self) -> None:
        self._once: dict[str, list[BaseException]] = {}
        self._lock = threading.Lock()

    def inject(self, stage: str, exc: BaseException | None = None) -> None:
        """Schedule ``exc`` (default ``RuntimeError``) to fire at this stage once."""
        if stage not in FAULT_STAGES:
            raise ValueError(f"unknown fault stage: {stage!r}")
        with self._lock:
            self._once.setdefault(stage, []).append(exc or RuntimeError(f"injected fault at {stage}"))

    def check(self, stage: str) -> None:
        """Raise the pending fault for this stage, consuming it."""
        with self._lock:
            pending = self._once.get(stage)
            if not pending:
                return
            exc = pending.pop(0)
            if not pending:
                self._once.pop(stage, None)
        raise exc

    def pending(self, stage: str) -> int:
        """How many faults are still queued for this stage."""
        with self._lock:
            return len(self._once.get(stage, ()))


class FakeEmbedder:
    """Hash-based deterministic embedder; same text always maps to same vector.

    Implements the surface :class:`RetrievalService` uses, so it can stand in
    without touching the network or loading weights.
    """

    def __init__(self, model_name: str = "fake-embedder", dim: int = 32) -> None:
        self.model_name = model_name
        self._dim = dim

    def instruction_fingerprint(self) -> str:
        return ""

    def _vector(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [digest[i % len(digest)] / 255.0 for i in range(self._dim)]

    def embed_documents(self, texts: Iterable[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, query: str) -> list[float]:
        return self._vector(query)


class FakeRetrieval:
    """Retrieval stand-in that returns no hits and reports itself usable."""

    def __init__(self, hits: list | None = None) -> None:
        self._hits = list(hits or [])
        self.searches: list[str] = []

    def search(self, query: str, top_k: int = 3) -> list:
        self.searches.append(query)
        return self._hits[:top_k]

    def config_fingerprint(self) -> str:
        return "fake-config"

    def verify_index(self) -> bool:
        return True

    def index_note(self, file_name: str) -> int:
        return 0

    def delete_note(self, file_name: str) -> None:
        return None


class FakeChatModel:
    """Scripted chat model: one queued reply per hop, streamed like a real one.

    ``bind_tools`` returns self because the graph calls it on every hop; the replies
    queue is consumed in order so a tool hop and its follow-up are explicit.
    """

    def __init__(self, replies: list, *, summary: str = "SUM") -> None:
        from langchain_core.messages import AIMessage

        self.replies = [r if isinstance(r, AIMessage) else AIMessage(content=str(r)) for r in replies]
        self.summary = summary
        self.calls: list[list] = []
        self.bound_tools: list = []

    def bind_tools(self, tools):
        self.bound_tools = list(tools)
        return self

    async def astream(self, messages, config=None):
        self.calls.append(list(messages))
        if not self.replies:
            raise AssertionError("FakeChatModel ran out of scripted replies")
        yield self.replies.pop(0)

    def invoke(self, messages, config=None):
        from langchain_core.messages import AIMessage

        return AIMessage(content=self.summary)

    async def ainvoke(self, messages, config=None):
        return self.invoke(messages, config)
