from pathlib import Path

from sentence_transformers import SentenceTransformer

from noteagent.retrieval.instructions import (
    MODEL_INSTRUCTIONS,
    instructions_for,
)

__all__ = [
    "MODEL_INSTRUCTIONS",
    "SentenceTransformerEmbedder",
    "build_embedder",
    "instructions_for",
]


class SentenceTransformerEmbedder:
    """Local sentence-transformers embedder with an on-disk model cache.

    ``query_prefix`` / ``document_prefix`` carry the model's own encoding instructions.
    Documents keep the *unprefixed* text as their citation content; the prefix only ever
    reaches the embedding, never the stored chunk text.
    """

    def __init__(
        self,
        model_name: str,
        cache_folder: Path,
        local_files_only: bool = False,
        *,
        query_prefix: str = "",
        document_prefix: str = "",
    ):
        cache_folder.mkdir(parents=True, exist_ok=True)
        self.model_name = model_name
        self.cache_folder = cache_folder
        self.query_prefix = query_prefix
        self.document_prefix = document_prefix
        self._model = SentenceTransformer(
            model_name,
            cache_folder=str(cache_folder),
            local_files_only=local_files_only,
        )

    def document_text(self, text: str) -> str:
        """Exact text handed to the model for a document."""
        return f"{self.document_prefix}{text}"

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Encode a batch of documents into vectors."""
        return self._model.encode([self.document_text(text) for text in texts]).tolist()

    def embed_query(self, query: str) -> list[float]:
        """Encode a single search query."""
        return self._model.encode([f"{self.query_prefix}{query}"]).tolist()[0]

    def instruction_fingerprint(self) -> str:
        """Compact description of the encoding instructions, for the index fingerprint."""
        if not self.query_prefix and not self.document_prefix:
            return ""
        return f"{self.query_prefix}|{self.document_prefix}"

    def max_tokens(self) -> int | None:
        """Input limit this model truncates at, if it reports one."""
        return int(getattr(self._model, "max_seq_length", 0)) or None

    def count_tokens(self, texts: list[str]) -> list[int]:
        """Token count per document text, using this model's own tokenizer.

        Special tokens are included on purpose: the budget that matters is what the
        model actually receives, not the visible character count.
        """
        prepared = [self.document_text(text) for text in texts]
        return [len(ids) for ids in self._model.tokenizer(prepared)["input_ids"]]


def build_embedder(
    model_name: str,
    cache_folder: Path,
    local_files_only: bool = False,
) -> SentenceTransformerEmbedder:
    """Create an embedder with the encoding instructions this model requires."""
    query_prefix, document_prefix = instructions_for(model_name)
    return SentenceTransformerEmbedder(
        model_name,
        cache_folder,
        local_files_only=local_files_only,
        query_prefix=query_prefix,
        document_prefix=document_prefix,
    )
