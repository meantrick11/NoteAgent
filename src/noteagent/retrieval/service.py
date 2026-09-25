import hashlib
import json
import time
from typing import Protocol

from noteagent.notes.repository import FileNoteRepository
from noteagent.observability.index_trace import IndexTrace
from noteagent.retrieval.chunker import MarkdownChunker
from noteagent.retrieval.instructions import instruction_fingerprint_for
from noteagent.retrieval.models import NoteChunk, SearchHit
from noteagent.retrieval.vector_store import ChromaVectorStore


class Embedder(Protocol):
    """Minimal embedding interface used by RetrievalService and tests."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, query: str) -> list[float]: ...


# 索引身份的版本：字段集合或含义变化时必须改，否则新旧指纹会被当成同一个索引。
INDEX_CONFIG_SCHEMA = "noteagent-index-v2"
# 笔记正文进入嵌入前的规范化版本（Markdown 标题解析等）；改了它旧索引就需要重建。
DOC_NORMALIZATION_VERSION = "md-v1"


def _elapsed_ms(started: float) -> int:
    """Milliseconds since started, using a monotonic clock."""
    return round((time.monotonic() - started) * 1000)


def canonical_index_config(
    *,
    model_id: str,
    chunker: MarkdownChunker,
    embed_heading_prefix: bool,
    instructions: str,
    resolved_revision: str | None = None,
) -> dict[str, object]:
    """Every field that decides what a stored vector and chunk offset mean.

    Anything here changing makes previously stored points incomparable, so all of it
    belongs in the identity; anything else about the deployment does not.
    """
    return {
        "schema": INDEX_CONFIG_SCHEMA,
        "normalization": DOC_NORMALIZATION_VERSION,
        "model": model_id,
        "revision": resolved_revision or "",
        "chunker": chunker.describe(),
        "heading_prefix": bool(embed_heading_prefix),
        "instructions": instructions,
    }


def fingerprint_of(canonical: dict[str, object]) -> str:
    """SHA-256 of the canonical JSON: the stable identity used for names and metadata."""
    payload = json.dumps(
        canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def index_config_fingerprint(
    chunker: MarkdownChunker,
    embedder: Embedder,
    embed_heading_prefix: bool,
    resolved_revision: str | None = None,
) -> str:
    """Identity of an index built by a concrete service (embedder already assembled)."""
    instructions = getattr(embedder, "instruction_fingerprint", None)
    return fingerprint_of(
        canonical_index_config(
            model_id=str(getattr(embedder, "model_name", "") or "unknown-model"),
            chunker=chunker,
            embed_heading_prefix=embed_heading_prefix,
            instructions=instructions() if callable(instructions) else "",
            resolved_revision=resolved_revision,
        )
    )


def index_fingerprint_for_model(
    model_id: str,
    *,
    strategy: str,
    embed_heading_prefix: bool,
    resolved_revision: str | None = None,
) -> str:
    """Identity a rebuild of this model would produce, without loading any weights.

    Needed *before* the rebuild so the target collection can be named from the identity
    it will actually have; the assembled service computes the same value from its own
    objects, and the rebuild refuses to publish if the two disagree.
    """
    return fingerprint_of(
        canonical_index_config(
            model_id=model_id,
            chunker=MarkdownChunker(strategy=strategy),
            embed_heading_prefix=embed_heading_prefix,
            instructions=instruction_fingerprint_for(model_id),
            resolved_revision=resolved_revision,
        )
    )



def index_targets(notes: FileNoteRepository) -> tuple[list[str], list[str]]:
    """Every indexable note, plus the files skipped on purpose.

    ``README.md`` is the data-directory description and ``bak/`` holds backups; the
    repository already treats both as not-notes, so a bulk rebuild must not quietly put
    them into the retrieval index. Shared by the CLI and the UI rebuild so the two can
    never disagree about what belongs in the index.
    """
    keep: list[str] = []
    skipped: list[str] = []
    for name in notes.list_notes():
        if name == "README.md" or name.split("/")[0] == "bak":
            skipped.append(name)
            continue
        keep.append(name)
    return keep, skipped


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
        resolved_revision: str | None = None,
    ):
        self._notes = notes
        self._chunker = chunker
        self._embedder = embedder
        self._store = store
        self._trace = trace or IndexTrace()
        self._embed_heading_prefix = embed_heading_prefix
        self._resolved_revision = resolved_revision
        # 构造即校验：配置与已有 collection 不符时立刻要求重建，而不是静默用错向量。
        self._store.ensure_config(self.config_fingerprint(), self.config_fields())

    def config_fields(self) -> dict[str, object]:
        """The verifiable configuration fields behind :meth:`config_fingerprint`."""
        instructions = getattr(self._embedder, "instruction_fingerprint", None)
        return canonical_index_config(
            model_id=str(getattr(self._embedder, "model_name", "") or "unknown-model"),
            chunker=self._chunker,
            embed_heading_prefix=self._embed_heading_prefix,
            instructions=instructions() if callable(instructions) else "",
            resolved_revision=self._resolved_revision,
        )

    def config_fingerprint(self) -> str:
        """Identity of the index this service would build."""
        return fingerprint_of(self.config_fields())

    def verify_index(self) -> bool:
        """True when the collection behind this service still exists and matches it.

        Cheap enough for a status or switch call, and deliberately re-reads the store:
        an index deleted by another process must stop counting as usable.
        """
        if not self._store.exists():
            return False
        return self._store.stored_config() == self.config_fingerprint()

    def point_count(self) -> int:
        """Number of stored vectors; 0 when the collection is gone."""
        return self._store.count()

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

    def indexed_files(self) -> set[str]:
        """Every note path with vectors in this collection.

        A full rebuild uses this to drop vectors of notes that no longer exist on disk;
        per-file upserts alone would leave those behind.
        """
        return self._store.list_file_names()

    def search(self, query: str, top_k: int = 3) -> list[SearchHit]:
        """Return the top_k nearest note chunks for the query."""
        embedding = self._embedder.embed_query(query)
        hits = self._store.query(embedding, top_k=top_k)
        top = hits[0].distance if hits else None
        self._trace.search(query, top_k, len(hits), top)
        return hits
