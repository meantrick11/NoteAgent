from pathlib import Path

from noteagent.notes.repository import FileNoteRepository
from noteagent.retrieval.chunker import MarkdownChunker
from noteagent.retrieval.service import RetrievalService
from noteagent.retrieval.vector_store import ChromaVectorStore


class FakeEmbedder:
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), 1.0] for text in texts]

    def embed_query(self, query: str) -> list[float]:
        return [float(len(query)), 1.0]


def test_index_and_search_roundtrip(tmp_path: Path):
    notes = FileNoteRepository(tmp_path / "notes")
    notes.create("LLM.md", "LLM")
    notes.write("LLM.md", "注意力机制用 Query Key Value 计算权重。\n", append=True)

    service = RetrievalService(
        notes=notes,
        chunker=MarkdownChunker(),
        embedder=FakeEmbedder(),
        store=ChromaVectorStore(tmp_path / "chroma", "test_knowledge"),
    )
    assert service.index_note("LLM.md") >= 1
    hits = service.search("注意力", top_k=2)
    assert hits
    assert hits[0].metadata["file_name"] == "LLM.md"
