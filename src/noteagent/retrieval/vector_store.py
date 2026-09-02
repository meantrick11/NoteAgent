from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings

from noteagent.retrieval.models import SearchHit


class ChromaVectorStore:
    """Persistent Chroma collection for note-chunk embeddings."""

    def __init__(self, persist_path: Path, collection_name: str):
        persist_path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=str(persist_path),
            settings=ChromaSettings(anonymized_telemetry_enabled=False),
        )
        self._collection = self._client.get_or_create_collection(collection_name)

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
