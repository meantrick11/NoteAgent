import json
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings
from chromadb.errors import NotFoundError

from noteagent.retrieval.models import SearchHit

# collection metadata 里的两条记录：索引身份（配置指纹的 SHA-256）与产生它的可核验字段。
# 只存指纹不够——排查"为什么要求重建"时要能读出到底是哪个字段变了。
CONFIG_FINGERPRINT_KEY = "noteagent_index_config"
CONFIG_FIELDS_KEY = "noteagent_index_config_fields"
# 加指纹之前建出来的 collection：身份无法核验，只能报告"需要重建"。
LEGACY_FINGERPRINT = "legacy:pre-fingerprint"


class IndexConfigMismatch(RuntimeError):
    """The existing collection was built with a different index configuration."""


class CollectionMissingError(RuntimeError):
    """The collection does not exist and the caller asked not to create one."""


def _is_fingerprint(value: object) -> bool:
    """True for a SHA-256 hex digest, i.e. a value written by this scheme."""
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


class ChromaVectorStore:
    """Persistent Chroma collection for note-chunk embeddings."""

    def __init__(
        self, persist_path: Path, collection_name: str, *, create_if_missing: bool = True
    ):
        """Open the collection, creating it only when the caller asked to build one.

        Reading an index must never create one: ``get_or_create_collection`` on a deleted
        collection would hand back an empty index and make a lost index look healthy.
        """
        persist_path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=str(persist_path),
            settings=ChromaSettings(anonymized_telemetry_enabled=False),
        )
        self._name = collection_name
        if create_if_missing:
            self._collection = self._client.get_or_create_collection(collection_name)
        else:
            live = self._live_collection()
            if live is None:
                raise CollectionMissingError(f"collection {collection_name!r} 不存在")
            self._collection = live

    @property
    def name(self) -> str:
        """Collection name, for diagnostics and user-facing messages."""
        return self._name

    def _live_collection(self):
        """The collection as it exists right now, or None when it is gone.

        Re-fetching instead of trusting the handle from construction is what makes a
        collection deleted by another process report as missing.
        """
        try:
            return self._client.get_collection(self._name)
        except NotFoundError:
            return None

    def exists(self) -> bool:
        """True when this collection is present. Never creates one."""
        return self._live_collection() is not None

    def count(self) -> int:
        """Number of stored vectors; 0 when the collection does not exist."""
        live = self._live_collection()
        return int(live.count()) if live is not None else 0

    def stored_config(self) -> str | None:
        """Index identity recorded in this collection, or None when it has none yet.

        A collection that predates fingerprinting but already holds vectors cannot be
        verified, so it reports the legacy sentinel rather than pretending to match; an
        empty one is safe to adopt because there are no vectors to reinterpret.
        """
        live = self._live_collection()
        stored = (live.metadata or {}).get(CONFIG_FINGERPRINT_KEY) if live else None
        if _is_fingerprint(stored):
            return str(stored)
        if live is not None and live.count():
            return LEGACY_FINGERPRINT
        return None

    def stored_config_fields(self) -> dict[str, object] | None:
        """The configuration fields recorded next to the fingerprint, for diagnostics."""
        live = self._live_collection()
        raw = (live.metadata or {}).get(CONFIG_FIELDS_KEY) if live else None
        if not isinstance(raw, str):
            return None
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    def ensure_config(self, fingerprint: str, fields: dict[str, object] | None = None) -> None:
        """Record what this index's vectors and offsets mean, or refuse to mix.

        Vectors, chunk boundaries and offsets are only comparable inside one
        configuration: a new embedding model, chunking strategy, or model revision makes
        every stored point meaningless, so reusing the collection would silently return
        garbage. An existing index whose identity differs (including one built before
        fingerprints existed) is refused instead of being relabelled.
        """
        stored = self.stored_config()
        if stored == fingerprint:
            return
        if stored is not None:
            raise IndexConfigMismatch(
                f"collection was built with {stored!r} but the current configuration is "
                f"{fingerprint!r}; rebuild the index before searching (旧向量与新配置不兼容)"
            )
        metadata = {**(self._collection.metadata or {}), CONFIG_FINGERPRINT_KEY: fingerprint}
        if fields is not None:
            metadata[CONFIG_FIELDS_KEY] = json.dumps(
                fields, ensure_ascii=False, sort_keys=True
            )
        self._collection.modify(metadata=metadata)

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
