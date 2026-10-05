"""Isolated application with production persistence, Git and vector services."""
from dataclasses import replace
from pathlib import Path

from NoteAgent.AppBootstrap.ChatAgentFactory import build_graph_agent
from NoteAgent.BusinessModules.ChatAgent.ChatTools import build_chat_tools
from NoteAgent.BusinessModules.ConversationState.ConversationCheckpoints import CheckpointRuntime
from NoteAgent.TechnicalSupport.DatabaseAccess import create_session_factory
from NoteAgent.BusinessModules.NoteStorage.MarkdownRepository import FileNoteRepository
from NoteAgent.BusinessModules.NoteStorage.NoteChanges import NoteMutationService
from NoteAgent.BusinessModules.NoteStorage.NoteVersions import NoteVersionStore
from NoteAgent.TechnicalSupport.NoteAccessControl.NoteAccessGate import WorkspaceGate
from NoteAgent.ApplicationFlows.ConversationRecovery.RecoveryCoordinator import RecoveryCoordinator
from NoteAgent.BusinessModules.NoteRetrieval.IndexRepair.IndexRepairService import IndexRepairService
from NoteAgent.BusinessModules.NoteRetrieval.NoteRetrievalService import RetrievalService
from NoteAgent.BusinessModules.NoteRetrieval.MarkdownChunker import MarkdownChunker
from NoteAgent.BusinessModules.NoteRetrieval.ChromaVectorStore import ChromaVectorStore
from Support.Fakes import FakeChatModel, FakeEmbedder
from Support.Harness import TEST_BUDGET
from Support.Webapp import build_checkpoint_app


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
