import hashlib
import time
from typing import Protocol

from noteagent.notes.repository import FileNoteRepository
from noteagent.observability.index_trace import IndexTrace
from noteagent.retrieval.chunker import MarkdownChunker
from noteagent.retrieval.models import NoteChunk, SearchHit
from noteagent.retrieval.vector_store import ChromaVectorStore


class Embedder(Protocol):
    """Minimal embedding interface used by RetrievalService and tests."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, query: str) -> list[float]: ...


def _elapsed_ms(started: float) -> int:
    """Milliseconds since started, using a monotonic clock."""
    return round((time.monotonic() - started) * 1000)


def index_config_fingerprint(
    chunker: MarkdownChunker, embedder: Embedder, embed_heading_prefix: bool
) -> str:
    """Describe what an index's vectors and offsets mean.

    Any change to the model, the chunking strategy, the text used for embedding, or the
    model's encoding instructions makes previously stored points incomparable, so the
    fingerprint must change too. Kept as a function so the rebuild script can compare
    without building a service.
    """
    model = str(getattr(embedder, "model_name", "") or "unknown-model")
    embed_text = "heading-prefix" if embed_heading_prefix else "content"
    parts = [chunker.describe(), model, embed_text]
    instructions = getattr(embedder, "instruction_fingerprint", None)
    if callable(instructions) and instructions():
        parts.append(instructions())
    return "|".join(parts)


class RetrievalService:
    """Chunk notes, write embeddings to Chroma, and search by query vector."""

    def __init__(
        self,
        notes: FileNoteRepository,
        chunker: MarkdownChunker,
        embedder: Embedder,
        store: ChromaVectorStore,
        trace: IndexTrace | None = None,
        *,
        embed_heading_prefix: bool = False,
    ):
        self._notes = notes
        self._chunker = chunker
        self._embedder = embedder
        self._store = store
        self._trace = trace or IndexTrace()
        self._embed_heading_prefix = embed_heading_prefix
        # 构造即校验：配置与已有 collection 不符时立刻要求重建，而不是静默用错向量。
        self._store.ensure_config(self.config_fingerprint())

    def config_fingerprint(self) -> str:
        """Fingerprint of the configuration this service would index with."""
        return index_config_fingerprint(
            self._chunker, self._embedder, self._embed_heading_prefix
        )

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
        chunks = self._chunker.split_with_metadata(content)
        if not chunks:
            self._trace.skip_empty(file_name)
            return 0
        self._trace.chunked(file_name, len(chunks), len(content))
        embed_started = time.monotonic()
        embeddings = self._embedder.embed_documents(
            [self._embed_text(chunk) for chunk in chunks]
        )
        self._trace.embedded(file_name, len(chunks), _elapsed_ms(embed_started))
        ids = [f"{file_name}_{index}" for index in range(len(chunks))]
        metadatas = [
            {
                "file_name": file_name,
                "chunk_index": index,
                "heading_path": chunk.heading_path,
                "start_char": chunk.start_char,
                "end_char": chunk.end_char,
                "content_sha256": hashlib.sha256(chunk.content.encode("utf-8")).hexdigest(),
            }
            for index, chunk in enumerate(chunks)
        ]
        upsert_started = time.monotonic()
        self._store.upsert(
            ids=ids,
            embeddings=embeddings,
            # documents 必须是可映射回原文的切片，引用与位置校验都依赖它。
            documents=[chunk.content for chunk in chunks],
            metadatas=metadatas,
        )
        self._trace.upserted(file_name, len(chunks), _elapsed_ms(upsert_started))
        self._trace.done(file_name, len(chunks), _elapsed_ms(started))
        return len(chunks)

    def _embed_text(self, chunk: NoteChunk) -> str:
        """Text handed to the embedder; may carry the section path, never the citation."""
        if not self._embed_heading_prefix or not chunk.heading_path:
            return chunk.content
        return f"{chunk.heading_path}\n{chunk.content}"

    def is_indexed(self, file_name: str) -> bool:
        """True if Chroma has at least one chunk for this relative path."""
        return self._store.has_file_name(file_name)

    def search(self, query: str, top_k: int = 3) -> list[SearchHit]:
        """Return the top_k nearest note chunks for the query."""
        embedding = self._embedder.embed_query(query)
        hits = self._store.query(embedding, top_k=top_k)
        top = hits[0].distance if hits else None
        self._trace.search(query, top_k, len(hits), top)
        return hits
