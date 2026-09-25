from pathlib import Path

from sentence_transformers import SentenceTransformer


class SentenceTransformerEmbedder:
    """Local sentence-transformers embedder with an on-disk model cache."""

    def __init__(
        self,
        model_name: str,
        cache_folder: Path,
        local_files_only: bool = False,
    ):
        cache_folder.mkdir(parents=True, exist_ok=True)
        self.model_name = model_name
        self.cache_folder = cache_folder
        self._model = SentenceTransformer(
            model_name,
            cache_folder=str(cache_folder),
            local_files_only=local_files_only,
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Encode a batch of texts into vectors."""
        return self._model.encode(texts).tolist()

    def embed_query(self, query: str) -> list[float]:
        """Encode a single search query."""
        return self._model.encode([query]).tolist()[0]

    def max_tokens(self) -> int | None:
        """Input limit this model truncates at, if it reports one."""
        return int(getattr(self._model, "max_seq_length", 0)) or None

    def count_tokens(self, texts: list[str]) -> list[int]:
        """Token count per text, using this model's own tokenizer.

        Special tokens are included on purpose: the budget that matters is what the
        model actually receives, not the visible character count.
        """
        return [len(ids) for ids in self._model.tokenizer(texts)["input_ids"]]
