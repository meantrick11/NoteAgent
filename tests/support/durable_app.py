"""Isolated application with production persistence, Git and vector services."""
from dataclasses import replace
from pathlib import Path

from noteagent.chat.session import build_graph_agent
from noteagent.chat.tools import build_chat_tools
from noteagent.conversations.checkpoints import CheckpointRuntime
from noteagent.db import create_session_factory
from noteagent.notes.repository import FileNoteRepository
from noteagent.notes.mutations import NoteMutationService
from noteagent.notes.versions import NoteVersionStore
from noteagent.recovery.gate import WorkspaceGate
from noteagent.recovery.service import RecoveryCoordinator
from noteagent.retrieval.repairs import IndexRepairService
from noteagent.retrieval.service import RetrievalService
from noteagent.retrieval.chunker import MarkdownChunker
from noteagent.retrieval.vector_store import ChromaVectorStore
from support.fakes import FakeChatModel, FakeEmbedder
from support.harness import TEST_BUDGET
from support.webapp import build_checkpoint_app


def build_durable_app(root: Path, sqlalchemy_url="sqlite:///:memory:", libpq_dsn=None, faults=None):
    app = build_checkpoint_app(root / "runtime", reply_batches=[[]], sqlalchemy_url=sqlalchemy_url)
    app.notes = FileNoteRepository(root / "notes")
    factory = create_session_factory(app.container.engine)
    gate = WorkspaceGate(factory, libpq_dsn=libpq_dsn)
    gate.ensure_row()
    versions = NoteVersionStore(root / "history", app.notes.root)
    repairs = IndexRepairService(factory, app.notes)
    retrieval = RetrievalService(notes=app.notes, chunker=MarkdownChunker(), embedder=FakeEmbedder(),
                                store=ChromaVectorStore(root / "chroma", "drill_notes"))
    mutations = NoteMutationService(app.notes, versions, gate, factory, repairs=repairs)
    if libpq_dsn:
        app.checkpoints = CheckpointRuntime.from_conn_string(libpq_dsn)
        # ConversationService stores this runtime under its public construction seam.
        app.service._runtime = app.checkpoints
    app.service._workspace_seq = lambda: gate.state().seq
    agent = build_graph_agent(model=FakeChatModel(["Recomputed reply"]),
        tools=build_chat_tools(app.notes, retrieval, app.drafts, repairs=repairs),
        notes=app.notes, drafts=app.drafts, budget=TEST_BUDGET, system_prompt="SYSTEM",
        service=app.service, checkpoints=app.checkpoints, retrieval=retrieval, mutations=mutations)
    container = app.container
    container.notes, container.workspace, container.versions = app.notes, gate, versions
    container.mutations, container.checkpoints, container.history_required = mutations, app.checkpoints, True
    container.model_runtime._workspace = gate
    container.model_runtime._snapshot = replace(container.model_runtime.snapshot(), chat_agent=agent, retrieval=retrieval)
    container.recovery = RecoveryCoordinator(session_factory=factory, gate=gate,
        conversations=app.service, mutations=mutations, repairs=repairs, notes=app.notes,
        retrieval_provider=lambda: retrieval, faults=faults)
    return app
