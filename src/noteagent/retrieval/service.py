import time
from typing import Protocol

from noteagent.notes.repository import FileNoteRepository
from noteagent.observability.index_trace import IndexTrace
from noteagent.retrieval.chunker import MarkdownChunker
from noteagent.retrieval.models import SearchHit
from noteagent.retrieval.vector_store import ChromaVectorStore


class Embedder(Protocol):
    """Minimal embedding interface used by RetrievalService and tests."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, query: str) -> list[float]: ...


def _elapsed_ms(started: float) -> int:
    """Milliseconds since started, using a monotonic clock."""
    return round((time.monotonic() - started) * 1000)


class RetrievalService:
    """Chunk notes, write embeddings to Chroma, and search by query vector."""

    def __init__(
        self,
        notes: FileNoteRepository,
        chunker: MarkdownChunker,
        embedder: Embedder,
        store: ChromaVectorStore,
        trace: IndexTrace | None = None,
    ):
        self._notes = notes
        self._chunker = chunker
        self._embedder = embedder
        self._store = store
        self._trace = trace or IndexTrace()

    def delete_note(self, file_name: str) -> None:
        """Drop every vector for this note. Safe if the file was never indexed."""
        started = time.monotonic()
        self._store.delete_by_file_name(file_name)
        self._trace.deleted(file_name, _elapsed_ms(started))

    def index_note(self, file_name: str) -> int:
        """Replace this file's vectors with a fresh split of the on-disk note.

        Deletes existing points first so a shorter rewrite cannot leave stale chunks.
        Returns the number of chunks written.
        """
        started = time.monotonic()
        self._trace.start(file_name)
        self.delete_note(file_name)
        content = self._notes.read(file_name)
        chunks = self._chunker.split(content)
        if not chunks:
            self._trace.skip_empty(file_name)
            return 0
        self._trace.chunked(file_name, len(chunks), len(content))
        embed_started = time.monotonic()
        embeddings = self._embedder.embed_documents(chunks)
        self._trace.embedded(file_name, len(chunks), _elapsed_ms(embed_started))
        ids = [f"{file_name}_{index}" for index in range(len(chunks))]
        metadatas = [
            {"file_name": file_name, "chunk_index": index}
            for index in range(len(chunks))
        ]
        upsert_started = time.monotonic()
        self._store.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=metadatas,
        )
        self._trace.upserted(file_name, len(chunks), _elapsed_ms(upsert_started))
        self._trace.done(file_name, len(chunks), _elapsed_ms(started))
        return len(chunks)

    def search(self, query: str, top_k: int = 3) -> list[SearchHit]:
        """Return the top_k nearest note chunks for the query."""
        embedding = self._embedder.embed_query(query)
        hits = self._store.query(embedding, top_k=top_k)
        top = hits[0].distance if hits else None
        self._trace.search(query, top_k, len(hits), top)
        return hits
