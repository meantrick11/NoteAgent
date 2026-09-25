from pathlib import Path

import pytest

from noteagent.chat.drafts import DraftStore, NoteDraft, commit_review
from noteagent.chat.history import ConversationStore
from noteagent.db import Base, create_engine_from_url, create_session_factory
from noteagent.notes.repository import FileNoteRepository
from noteagent.retrieval.chunker import MarkdownChunker
from noteagent.retrieval.service import RetrievalService
from noteagent.retrieval.vector_store import ChromaVectorStore, IndexConfigMismatch

_INDEX_TRACE = "noteagent.observability.index_trace"


class FakeEmbedder:
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), 1.0] for text in texts]

    def embed_query(self, query: str) -> list[float]:
        return [float(len(query)), 1.0]


def _service(tmp_path: Path, embedder=None) -> tuple[FileNoteRepository, RetrievalService]:
    notes = FileNoteRepository(tmp_path / "notes")
    service = RetrievalService(
        notes=notes,
        chunker=MarkdownChunker(),
        embedder=embedder or FakeEmbedder(),
        store=ChromaVectorStore(tmp_path / "chroma", "test_knowledge"),
    )
    return notes, service


def test_index_and_search_roundtrip(tmp_path: Path):
    notes, service = _service(tmp_path)
    notes.create("LLM.md", "LLM")
    notes.write("LLM.md", "注意力机制用 Query Key Value 计算权重。\n", append=True)

    assert service.index_note("LLM.md") >= 1
    hits = service.search("注意力", top_k=2)
    assert hits
    assert hits[0].metadata["file_name"] == "LLM.md"


def test_reindex_drops_stale_chunks(tmp_path: Path):
    stale = "STALE_UNIQUE_PHRASE_XYZ " * 40
    notes, service = _service(tmp_path)
    notes.create("Go.md", "Go")
    notes.write("Go.md", stale + "\n", append=True)
    service.index_note("Go.md")
    notes.write("Go.md", "# Go\n\nNEW_ONLY_PHRASE\n", append=False)
    service.index_note("Go.md")
    got = service._store._collection.get(
        where={"file_name": "Go.md"},
        include=["documents"],
    )
    docs = got.get("documents") or []
    assert docs
    assert all("STALE_UNIQUE_PHRASE_XYZ" not in text for text in docs)
    assert any("NEW_ONLY_PHRASE" in text for text in docs)


def test_delete_note_removes_hits(tmp_path: Path):
    notes, service = _service(tmp_path)
    notes.create("Go.md", "Go")
    notes.write("Go.md", "注意力机制用 Query Key Value 计算权重。\n", append=True)
    service.index_note("Go.md")
    notes.delete("Go.md")
    service.delete_note("Go.md")
    got = service._store._collection.get(where={"file_name": "Go.md"})
    assert not (got.get("ids") or [])


def test_index_note_logs_steps(tmp_path: Path, caplog):
    unique = "UNIQUE_BODY_NOT_IN_LOGS_XYZ"
    notes, service = _service(tmp_path)
    notes.create("Go.md", "Go")
    notes.write("Go.md", unique + "\n", append=True)
    with caplog.at_level("INFO", logger=_INDEX_TRACE):
        service.index_note("Go.md")
    text = caplog.text
    assert "index start file=Go.md" in text
    assert "index delete file=Go.md" in text
    assert "index chunked file=Go.md" in text
    assert "index embedded file=Go.md" in text
    assert "index upserted file=Go.md" in text
    assert "index done file=Go.md" in text
    assert unique not in text
    assert "chroma delete" not in text


class _EmptyChunker:
    def split(self, content: str) -> list[str]:
        return []

    def split_with_metadata(self, content: str) -> list[object]:
        return []

    def describe(self) -> str:
        return "empty-chunker"


def test_index_skip_empty_logs(tmp_path: Path, caplog):
    notes = FileNoteRepository(tmp_path / "notes")
    notes.create("Go.md", "Go")
    service = RetrievalService(
        notes=notes,
        chunker=_EmptyChunker(),
        embedder=FakeEmbedder(),
        store=ChromaVectorStore(tmp_path / "chroma", "test_empty"),
    )
    with caplog.at_level("INFO", logger=_INDEX_TRACE):
        assert service.index_note("Go.md") == 0
    text = caplog.text
    assert "index start file=Go.md" in text
    assert "index skip empty file=Go.md" in text
    assert "index chunked" not in text
    assert "index embedded" not in text
    assert "index upserted" not in text


def test_commit_review_create_is_searchable(tmp_path: Path):
    notes, service = _service(tmp_path)
    engine = create_engine_from_url("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    history = ConversationStore(create_session_factory(engine))
    conv = history.create("t")
    store = DraftStore(history)
    store.put(conv.id, NoteDraft(
        action="create",
        file_name="Go.md",
        content="注意力机制用 Query Key Value 计算权重。\n",
    ))
    result = commit_review(notes, store, conv.id, "approve", retrieval=service)
    assert result["status"] == "written"
    hits = service.search("注意力", top_k=2)
    assert hits
    assert hits[0].metadata["file_name"] == "Go.md"


# --- 任务六：位置与章节元数据、配置指纹 ---------------------------------------

HEAVY_NOTE = (
    "# 根\n\n## 第一节\n\n回溯是递归的副产品，有递归必有回溯。\n\n"
    "```python\n# 这是代码注释，不是标题\nx = 1\n```\n\n## 第二节\n\n队列用于层序遍历。\n"
)


def test_index_records_offsets_and_heading_paths(tmp_path: Path):
    notes = FileNoteRepository(tmp_path / "notes")
    notes.create("Tree.md", "Tree")
    notes.write("Tree.md", HEAVY_NOTE, append=False)
    service = RetrievalService(
        notes=notes,
        chunker=MarkdownChunker(chunk_size=500, chunk_overlap=0, strategy="heading"),
        embedder=FakeEmbedder(),
        store=ChromaVectorStore(tmp_path / "chroma", "meta"),
    )
    service.index_note("Tree.md")
    body = (tmp_path / "notes" / "Tree.md").read_text(encoding="utf-8")
    metas = (
        service._store._collection.get(where={"file_name": "Tree.md"}, include=["metadatas"]).get("metadatas") or []
    )
    docs = (
        service._store._collection.get(where={"file_name": "Tree.md"}, include=["documents"]).get("documents") or []
    )
    assert metas and docs
    for meta, document in zip(metas, docs):
        assert body[meta["start_char"] : meta["end_char"]] == document
        assert meta["content_sha256"]
        assert meta["heading_path"].startswith("根")


def test_heading_prefix_changes_only_the_embedded_text(tmp_path: Path):
    class RecordingEmbedder(FakeEmbedder):
        def __init__(self):
            self.seen: list[str] = []

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            self.seen.extend(texts)
            return super().embed_documents(texts)

    notes = FileNoteRepository(tmp_path / "notes")
    notes.create("Tree.md", "Tree")
    notes.write("Tree.md", HEAVY_NOTE, append=False)
    embedder = RecordingEmbedder()
    service = RetrievalService(
        notes=notes,
        chunker=MarkdownChunker(chunk_size=500, chunk_overlap=0, strategy="heading"),
        embedder=embedder,
        store=ChromaVectorStore(tmp_path / "chroma", "prefix"),
        embed_heading_prefix=True,
    )
    service.index_note("Tree.md")
    assert any("根 > 第一节" in text for text in embedder.seen)
    docs = (service._store._collection.get(where={"file_name": "Tree.md"}, include=["documents"]).get("documents") or [])
    assert all("根 > 第一节" not in document for document in docs)


def test_reusing_a_collection_with_another_configuration_is_refused(tmp_path: Path):
    notes = FileNoteRepository(tmp_path / "notes")
    notes.create("Tree.md", "Tree")
    notes.write("Tree.md", HEAVY_NOTE, append=False)
    store = ChromaVectorStore(tmp_path / "chroma", "shared")
    RetrievalService(
        notes=notes,
        chunker=MarkdownChunker(500, 50, strategy="char"),
        embedder=FakeEmbedder(),
        store=store,
    ).index_note("Tree.md")
    with pytest.raises(IndexConfigMismatch):
        RetrievalService(
            notes=notes,
            chunker=MarkdownChunker(500, 50, strategy="heading"),
            embedder=FakeEmbedder(),
            store=ChromaVectorStore(tmp_path / "chroma", "shared"),
        )


def test_a_collection_from_before_fingerprints_is_adopted(tmp_path: Path):
    from noteagent.retrieval.vector_store import LEGACY_FINGERPRINT

    store = ChromaVectorStore(tmp_path / "chroma", "legacy")
    store.upsert(
        ids=["Go.md_0"],
        embeddings=[[1.0, 2.0]],
        documents=["旧内容"],
        metadatas=[{"file_name": "Go.md", "chunk_index": 0}],
    )
    store.ensure_config(LEGACY_FINGERPRINT)
    with pytest.raises(IndexConfigMismatch):
        store.ensure_config("heading:500/50|all-MiniLM-L6-v2|content")
