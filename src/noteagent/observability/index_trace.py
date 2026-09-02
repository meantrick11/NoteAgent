import logging

_logger = logging.getLogger(__name__)


class IndexTrace:
    """Log retrieval index/search steps. Does not chunk, embed, or write Chroma."""

    def start(self, file_name: str) -> None:
        _logger.info("index start file=%s", file_name)

    def deleted(self, file_name: str, elapsed_ms: int) -> None:
        _logger.info("index delete file=%s elapsed_ms=%d", file_name, elapsed_ms)

    def chunked(self, file_name: str, chunks: int, chars: int) -> None:
        _logger.info(
            "index chunked file=%s chunks=%d chars=%d",
            file_name,
            chunks,
            chars,
        )

    def embedded(self, file_name: str, chunks: int, elapsed_ms: int) -> None:
        _logger.info(
            "index embedded file=%s chunks=%d elapsed_ms=%d",
            file_name,
            chunks,
            elapsed_ms,
        )

    def upserted(self, file_name: str, chunks: int, elapsed_ms: int) -> None:
        _logger.info(
            "index upserted file=%s chunks=%d elapsed_ms=%d",
            file_name,
            chunks,
            elapsed_ms,
        )

    def done(self, file_name: str, chunks: int, elapsed_ms: int) -> None:
        _logger.info(
            "index done file=%s chunks=%d elapsed_ms=%d",
            file_name,
            chunks,
            elapsed_ms,
        )

    def skip_empty(self, file_name: str) -> None:
        _logger.info("index skip empty file=%s", file_name)

    def search(
        self,
        query: str,
        top_k: int,
        hits: int,
        top_distance: float | None,
    ) -> None:
        _logger.info(
            "search query=%.80s top_k=%d hits=%d top_distance=%s",
            query,
            top_k,
            hits,
            top_distance,
        )
