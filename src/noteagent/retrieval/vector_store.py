from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings

from noteagent.retrieval.models import SearchHit

# 存进 collection metadata 的配置指纹键。
CONFIG_FINGERPRINT_KEY = "noteagent_index_config"
# 加指纹之前建出来的索引，等价于当时的默认配置。
LEGACY_FINGERPRINT = "char:500/50|all-MiniLM-L6-v2|content"


class IndexConfigMismatch(RuntimeError):
    """The existing collection was built with a different index configuration."""


class ChromaVectorStore:
    """Persistent Chroma collection for note-chunk embeddings."""

    def __init__(self, persist_path: Path, collection_name: str):
        persist_path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=str(persist_path),
            settings=ChromaSettings(anonymized_telemetry_enabled=False),
        )
        self._collection = self._client.get_or_create_collection(collection_name)

    def stored_config(self) -> str | None:
        """Fingerprint recorded in this collection, or None when it has none yet."""
        stored = (self._collection.metadata or {}).get(CONFIG_FINGERPRINT_KEY)
        if stored is None and self._collection.count():
            return LEGACY_FINGERPRINT
        return stored

    def ensure_config(self, fingerprint: str) -> None:
        """Record what this index's vectors and offsets mean, or refuse to mix.

        Vectors, chunk boundaries and offsets are only comparable inside one
        configuration: a new embedding model or a new chunking strategy makes every
        stored point meaningless, so reusing the collection would silently return
        garbage. A collection built before fingerprints existed counts as the legacy
        default, which lets an unchanged deployment keep working while catching a
        changed one.
        """
        stored = (self._collection.metadata or {}).get(CONFIG_FINGERPRINT_KEY)
        if stored is None and self._collection.count():
            stored = LEGACY_FINGERPRINT
        if stored == fingerprint:
            return
        if stored is not None:
            raise IndexConfigMismatch(
                f"collection was built with {stored!r} but the current configuration is "
                f"{fingerprint!r}; rebuild the index before searching (旧向量与新配置不兼容)"
            )
        self._collection.modify(
            metadata={**(self._collection.metadata or {}), CONFIG_FINGERPRINT_KEY: fingerprint}
        )

    def upsert(
        self,
        *,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, object]],
    ) -> None:
        """Insert or replace chunks by id."""
        self._collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

    def delete_by_file_name(self, file_name: str) -> None:
        """Remove all chunks whose metadata file_name matches. No-op if none exist."""
        self._collection.delete(where={"file_name": file_name})

    def has_file_name(self, file_name: str) -> bool:
        """True if any chunk is stored for this relative note path."""
        got = self._collection.get(where={"file_name": file_name}, include=["metadatas"])
        return bool(got.get("ids"))

    def list_file_names(self) -> set[str]:
        """Every note path that currently has vectors in this collection.

        A full rebuild needs this to drop vectors of notes that no longer exist on disk:
        per-file upserts alone would leave those behind forever.
        """
        got = self._collection.get(include=["metadatas"])
        names: set[str] = set()
        for metadata in got.get("metadatas") or []:
            value = (metadata or {}).get("file_name")
            if value:
                names.add(str(value))
        return names

    def query(self, embedding: list[float], top_k: int) -> list[SearchHit]:
        """Nearest-neighbor search; empty Chroma fields become empty hits."""
        results = self._collection.query(
            query_embeddings=[embedding],
            n_results=top_k,
            include=["documents", "distances", "metadatas"],
        )
        documents = (results.get("documents") or [[]])[0]
        distances = (results.get("distances") or [[]])[0]
        metadatas = (results.get("metadatas") or [[]])[0]
        hits: list[SearchHit] = []
        for content, distance, metadata in zip(documents, distances, metadatas):
            hits.append(
                SearchHit(
                    content=content or "",
                    distance=float(distance),
                    metadata=dict(metadata or {}),
                )
            )
        return hits
