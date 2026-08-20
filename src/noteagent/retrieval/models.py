from dataclasses import dataclass


@dataclass(frozen=True)
class SearchHit:
    """One retrieved chunk: text, distance, and Chroma metadata."""

    content: str
    distance: float
    metadata: dict[str, object]
