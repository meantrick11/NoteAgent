from pathlib import Path

from noteagent.chat.drafts import DraftStore, NoteDraft, commit_review
from noteagent.notes.repository import FileNoteRepository
from noteagent.retrieval.chunker import MarkdownChunker
from noteagent.retrieval.service import RetrievalService
from noteagent.retrieval.vector_store import ChromaVectorStore

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
    store = DraftStore()
    store.put("t1", NoteDraft(
        action="create",
        file_name="Go.md",
        content="注意力机制用 Query Key Value 计算权重。\n",
    ))
    result = commit_review(notes, store, "t1", "approve", retrieval=service)
    assert result["status"] == "written"
    hits = service.search("注意力", top_k=2)
    assert hits
    assert hits[0].metadata["file_name"] == "Go.md"
