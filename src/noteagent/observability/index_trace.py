import logging

_logger = logging.getLogger(__name__)


class IndexTrace:
    """INFO logs for retrieval index and search steps. Does not chunk, embed, or write Chroma."""

    def start(self, file_name: str) -> None:
        """Log that ``index_note`` has started a full rebuild for this file."""
        _logger.info("index start file=%s", file_name)

    def deleted(self, file_name: str, elapsed_ms: int) -> None:
        """Log that all Chroma points for this file were dropped (no-op if none existed)."""
        _logger.info("index delete file=%s elapsed_ms=%d", file_name, elapsed_ms)

    def chunked(self, file_name: str, chunks: int, chars: int) -> None:
        """Log how many chunks ``index_note`` split from the on-disk note (``chars`` is full-file length)."""
        _logger.info(
            "index chunked file=%s chunks=%d chars=%d",
            file_name,
            chunks,
            chars,
        )

    def embedded(self, file_name: str, chunks: int, elapsed_ms: int) -> None:
        """Log that ``index_note`` finished embedding every chunk of this file."""
        _logger.info(
            "index embedded file=%s chunks=%d elapsed_ms=%d",
            file_name,
            chunks,
            elapsed_ms,
        )

    def upserted(self, file_name: str, chunks: int, elapsed_ms: int) -> None:
        """Log that ``index_note`` wrote this file's rebuilt chunks to Chroma (full-file upsert, not per-chunk)."""
        _logger.info(
            "index upserted file=%s chunks=%d elapsed_ms=%d",
            file_name,
            chunks,
            elapsed_ms,
        )

    def done(self, file_name: str, chunks: int, elapsed_ms: int) -> None:
        """Log that ``index_note`` finished a successful rebuild (``elapsed_ms`` covers the whole call)."""
        _logger.info(
            "index done file=%s chunks=%d elapsed_ms=%d",
            file_name,
            chunks,
            elapsed_ms,
        )

    def skip_empty(self, file_name: str) -> None:
        """Log that ``index_note`` stopped after an empty split: old points are gone and nothing was written."""
        _logger.info("index skip empty file=%s", file_name)

    def search(
        self,
        query: str,
        top_k: int,
        hits: int,
        top_distance: float | None,
    ) -> None:
        """Log one ``search`` query: requested ``top_k``, hit count, and best distance (None if no hits)."""
        _logger.info(
            "search query=%.80s top_k=%d hits=%d top_distance=%s",
            query,
            top_k,
            hits,
            top_distance,
        )
