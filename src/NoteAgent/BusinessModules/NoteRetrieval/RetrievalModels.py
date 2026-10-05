from dataclasses import dataclass


@dataclass(frozen=True)
class SearchHit:
    """One retrieved chunk: text, distance, and Chroma metadata."""

    content: str
    distance: float
    metadata: dict[str, object]


@dataclass(frozen=True, slots=True)
class NoteChunk:
    """One indexable fragment: verbatim text, its note offsets, and its section path.

    ``content`` is always a slice of the note text, so a citation built from it can be
    located back in the note; the text used for embedding may differ (see the chunker
    and ``RetrievalService``).
    """

    content: str
    heading_path: str
    start_char: int
    end_char: int
