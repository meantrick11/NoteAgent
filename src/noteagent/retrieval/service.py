import logging
from typing import Protocol

from noteagent.notes.repository import FileNoteRepository
from noteagent.retrieval.chunker import MarkdownChunker
from noteagent.retrieval.models import SearchHit
from noteagent.retrieval.vector_store import ChromaVectorStore

_logger = logging.getLogger(__name__)


class Embedder(Protocol):
    """Minimal embedding interface used by RetrievalService and tests."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, query: str) -> list[float]: ...


class RetrievalService:
    """Chunk notes, write embeddings to Chroma, and search by query vector."""

    def __init__(
        self,
        notes: FileNoteRepository,
        chunker: MarkdownChunker,
        embedder: Embedder,
        store: ChromaVectorStore,
    ):
        self._notes = notes
        self._chunker = chunker
        self._embedder = embedder
        self._store = store

    def index_note(self, file_name: str) -> int:
        """Index one note. Returns the number of chunks written."""
        content = self._notes.read(file_name)
        chunks = self._chunker.split(content)
        if not chunks:
            _logger.info("index skip empty file=%s", file_name)
            return 0
        embeddings = self._embedder.embed_documents(chunks)
        ids = [f"{file_name}_{index}" for index in range(len(chunks))]
        metadatas = [
            {"file_name": file_name, "chunk_index": index}
            for index in range(len(chunks))
        ]
        self._store.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=metadatas,
        )
        _logger.info("index file=%s chunks=%d", file_name, len(chunks))
        return len(chunks)

    def search(self, query: str, top_k: int = 3) -> list[SearchHit]:
        """Return the top_k nearest note chunks for the query."""
        embedding = self._embedder.embed_query(query)
        hits = self._store.query(embedding, top_k=top_k)
        top = hits[0].distance if hits else None
        _logger.info(
            "search query=%.80s top_k=%d hits=%d top_distance=%s",
            query,
            top_k,
            len(hits),
            top,
        )
        return hits
