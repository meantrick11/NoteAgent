from pathlib import Path

import chromadb
import pytest
from chromadb.config import Settings as ChromaSettings

from noteagent.chat.drafts import DraftStore, NoteDraft, commit_review
from noteagent.chat.history import ConversationStore
from noteagent.db import Base, create_engine_from_url, create_session_factory
from noteagent.model_management.service import (
    COLLECTION_DIGEST_LENGTH,
    COLLECTION_MAX_LENGTH,
    embedding_collection_name,
)
from noteagent.notes.repository import FileNoteRepository
from noteagent.retrieval.chunker import MarkdownChunker
from noteagent.retrieval.service import RetrievalService, index_config_fingerprint
from noteagent.retrieval.vector_store import (
    LEGACY_FINGERPRINT,
    ChromaVectorStore,
    CollectionMissingError,
    IndexConfigMismatch,
)

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


# --- 任务三/四：索引身份、存在性与空索引 ---------------------------------------


def _collection_names(chroma_dir: Path) -> set[str]:
    """Every collection currently in the store, read without creating anything."""
    client = chromadb.PersistentClient(
        path=str(chroma_dir),
        settings=ChromaSettings(anonymized_telemetry_enabled=False),
    )
    return {collection.name for collection in client.list_collections()}


def _indexed_service(tmp_path: Path, name: str = "demo") -> RetrievalService:
    """A real Chroma collection with one indexed note."""
    notes = FileNoteRepository(tmp_path / "notes")
    notes.create("Go.md", "Go")
    notes.write("Go.md", "注意力机制用 Query Key Value 计算权重。\n", append=True)
    service = RetrievalService(
        notes=notes,
        chunker=MarkdownChunker(),
        embedder=FakeEmbedder(),
        store=ChromaVectorStore(tmp_path / "chroma", name),
    )
    service.index_note("Go.md")
    return service


def test_opening_a_missing_collection_refuses_and_creates_nothing(tmp_path: Path):
    """A lost index must not be silently replaced by an empty one."""
    with pytest.raises(CollectionMissingError):
        ChromaVectorStore(tmp_path / "chroma", "absent", create_if_missing=False)

    assert _collection_names(tmp_path / "chroma") == set()


def test_a_collection_created_for_a_rebuild_is_reported_as_empty(tmp_path: Path):
    """An index built for an empty corpus is valid, and says it holds nothing."""
    store = ChromaVectorStore(tmp_path / "chroma", "fresh")

    assert store.exists() is True
    assert store.count() == 0
    # 空 collection 还没有向量需要重新解释，可以就地确定身份。
    assert store.stored_config() is None
    service = RetrievalService(
        notes=FileNoteRepository(tmp_path / "notes"),
        chunker=MarkdownChunker(),
        embedder=FakeEmbedder(),
        store=store,
    )
    assert service.verify_index() is True
    assert service.point_count() == 0


def test_a_collection_from_before_fingerprints_is_reported_as_needing_a_rebuild(tmp_path: Path):
    """旧格式 collection 的身份无法核验，不能被当成匹配。"""
    store = ChromaVectorStore(tmp_path / "chroma", "legacy")
    store.upsert(
        ids=["Go.md_0"],
        embeddings=[[1.0, 2.0]],
        documents=["旧内容"],
        metadatas=[{"file_name": "Go.md", "chunk_index": 0}],
    )
    assert store.stored_config() == LEGACY_FINGERPRINT

    with pytest.raises(IndexConfigMismatch):
        RetrievalService(
            notes=FileNoteRepository(tmp_path / "notes"),
            chunker=MarkdownChunker(),
            embedder=FakeEmbedder(),
            store=ChromaVectorStore(tmp_path / "chroma", "legacy"),
        )


def test_an_empty_legacy_collection_is_adopted_with_the_current_identity(tmp_path: Path):
    """没有向量要重新解释时，旧 collection 可以就地写上新身份。"""
    ChromaVectorStore(tmp_path / "chroma", "legacy")
    service = RetrievalService(
        notes=FileNoteRepository(tmp_path / "notes"),
        chunker=MarkdownChunker(),
        embedder=FakeEmbedder(),
        store=ChromaVectorStore(tmp_path / "chroma", "legacy"),
    )

    assert service.verify_index() is True
    assert (
        ChromaVectorStore(tmp_path / "chroma", "legacy").stored_config()
        == service.config_fingerprint()
    )


def test_a_deleted_collection_stops_counting_as_usable(tmp_path: Path):
    """删除活动 collection 后，索引必须立刻报为不可用，而不是一个空索引。"""
    service = _indexed_service(tmp_path)
    assert service.verify_index() is True
    assert service.point_count() > 0

    client = chromadb.PersistentClient(
        path=str(tmp_path / "chroma"),
        settings=ChromaSettings(anonymized_telemetry_enabled=False),
    )
    client.delete_collection("demo")

    assert service.verify_index() is False
    assert service.point_count() == 0
    assert _collection_names(tmp_path / "chroma") == set()


def test_two_configurations_of_one_model_land_in_different_collections(tmp_path: Path):
    """Same model, different chunking: separate identities, separate collections."""
    plain = FakeEmbedder()
    char = index_config_fingerprint(MarkdownChunker(500, 50, strategy="char"), plain, False)
    heading = index_config_fingerprint(
        MarkdownChunker(500, 50, strategy="heading"), plain, False
    )

    assert char != heading
    assert embedding_collection_name("notes", "e5", char) != embedding_collection_name(
        "notes", "e5", heading
    )


def test_a_long_collection_name_never_truncates_the_identity(tmp_path: Path):
    """名字有长度上限，但指纹摘要必须完整保留，否则两个身份会被截成同名。"""
    base = "a_very_long_base_collection_name_that_does_not_fit_at_all"
    first = embedding_collection_name(base, "intfloat/multilingual-e5-small", "a" * 64)
    second = embedding_collection_name(base, "intfloat/multilingual-e5-small", "b" * 64)

    assert len(first) <= COLLECTION_MAX_LENGTH
    assert first != second
    assert first.endswith("a" * COLLECTION_DIGEST_LENGTH)
    assert second.endswith("b" * COLLECTION_DIGEST_LENGTH)
