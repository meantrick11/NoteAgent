"""Durable per-file index repairs: pending/ready/failed, fencing and restart."""

from __future__ import annotations

import pytest

from noteagent.db import Base, create_engine_from_url, create_session_factory, load_all_models
from noteagent.notes.repository import FileNoteRepository
from noteagent.retrieval.chunker import MarkdownChunker
from noteagent.retrieval.repairs import FAILED, READY, IndexRepairService
from noteagent.retrieval.service import RetrievalService
from noteagent.retrieval.vector_store import ChromaVectorStore


class FakeEmbedder:
    def __init__(self, model_name: str = "fake"):
        self.model_name = model_name

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), 1.0] for text in texts]

    def embed_query(self, query: str) -> list[float]:
        return [float(len(query)), 1.0]


@pytest.fixture
def env(tmp_path):
    notes = FileNoteRepository(tmp_path / "notes")
    retrieval = RetrievalService(
        notes=notes,
        chunker=MarkdownChunker(),
        embedder=FakeEmbedder(),
        store=ChromaVectorStore(tmp_path / "chroma", "repair_knowledge"),
    )
    load_all_models()
    engine = create_engine_from_url("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    repairs = IndexRepairService(factory, notes)
    return notes, retrieval, repairs, factory


def test_repair_marks_ready_and_search_is_fenced_by_sync(env):
    notes, retrieval, repairs, _ = env
    notes.create("A.md", "A")
    notes.write("A.md", "注意力机制用 Query Key Value。\n", append=True)

    status = repairs.repair("A.md", retrieval, operation_id="op-a")
    assert status.status == READY and status.synced
    assert repairs.is_synced("A.md", retrieval)
    hits = repairs.search_synced(retrieval, "注意力", top_k=2)
    assert [h.metadata["file_name"] for h in hits] == ["A.md"]


def test_only_changed_file_is_repaired(env):
    notes, retrieval, repairs, _ = env
    notes.create("A.md", "A")
    notes.write("A.md", "alpha\n", append=True)
    notes.create("B.md", "B")
    notes.write("B.md", "beta\n", append=True)
    repairs.repair_many(["A.md", "B.md"], retrieval, operation_id="op-init")
    b_before = repairs.status("B.md")

    notes.write("A.md", "changed\n", append=True)
    repairs.repair("A.md", retrieval, operation_id="op-a2")

    b_after = repairs.status("B.md")
    # B was not touched: same ledger record and still synced.
    assert b_after["operation_id"] == b_before["operation_id"]
    assert b_after["attempts"] == b_before["attempts"]
    assert repairs.is_synced("B.md", retrieval)


def test_delete_leaves_zero_vectors(env):
    notes, retrieval, repairs, _ = env
    notes.create("A.md", "A")
    notes.write("A.md", "gone soon\n", append=True)
    repairs.repair("A.md", retrieval, operation_id="op-1")
    notes.delete("A.md")

    status = repairs.repair("A.md", retrieval, operation_id="op-2")
    assert status.status == READY
    assert not retrieval.is_indexed("A.md")
    assert repairs.is_synced("A.md", retrieval)


def test_empty_document_is_a_legal_zero_chunk(env):
    notes, retrieval, repairs, _ = env
    (notes.root / "E.md").write_bytes(b"   \n")

    status = repairs.repair("E.md", retrieval, operation_id="op-e")
    assert status.status == READY
    assert not retrieval.is_indexed("E.md")
    assert repairs.is_synced("E.md", retrieval)


def test_failure_keeps_repair_and_fences_stale_search(env, monkeypatch):
    notes, retrieval, repairs, _ = env
    notes.create("A.md", "A")
    notes.write("A.md", "注意力机制。\n", append=True)
    repairs.repair("A.md", retrieval, operation_id="op-1")
    assert repairs.search_synced(retrieval, "注意力")

    # The body changes, then the vector update fails midway.
    notes.write("A.md", "完全不同的新正文\n", append=True)

    def boom(path):
        raise RuntimeError("embedding interrupted")

    monkeypatch.setattr(retrieval, "index_note", boom)
    status = repairs.repair("A.md", retrieval, operation_id="op-2")
    assert status.status == FAILED and not status.synced
    # Stale vectors must not be surfaced for the changed body.
    assert repairs.search_synced(retrieval, "注意力", top_k=3) == []


def test_fingerprint_change_marks_unsynced(env, monkeypatch):
    notes, retrieval, repairs, _ = env
    notes.create("A.md", "A")
    notes.write("A.md", "body\n", append=True)
    repairs.repair("A.md", retrieval, operation_id="op-1")
    assert repairs.is_synced("A.md", retrieval)

    monkeypatch.setattr(retrieval, "config_fingerprint", lambda: "different-config")
    assert not repairs.is_synced("A.md", retrieval)


def test_reconcile_retries_failed_repairs_after_restart(env, monkeypatch):
    notes, retrieval, repairs, factory = env
    notes.create("A.md", "A")
    notes.write("A.md", "recover me\n", append=True)

    def boom(path):
        raise RuntimeError("down")

    monkeypatch.setattr(retrieval, "index_note", boom)
    repairs.repair("A.md", retrieval, operation_id="op-fail")
    assert repairs.status("A.md")["status"] == FAILED

    # A fresh service instance (restart) retries the same failed path.
    monkeypatch.undo()
    restarted = IndexRepairService(factory, notes)
    results = restarted.reconcile(retrieval, operation_id="reconcile")
    assert any(r.path == "A.md" and r.status == READY for r in results)
    assert restarted.is_synced("A.md", retrieval)
