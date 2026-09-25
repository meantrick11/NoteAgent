from langchain_text_splitters import RecursiveCharacterTextSplitter

from noteagent.retrieval.markdown import heading_path_at, note_headings
from noteagent.retrieval.models import NoteChunk

STRATEGIES = ("char", "heading")


class MarkdownChunker:
    """Split Markdown into embeddable chunks, preferring Chinese punctuation.

    Two strategies, both keeping ``split()`` behaviour for callers that only want text:

    - ``char``: length-based recursive splitting. Chunks may cross section boundaries;
      this is the production baseline that the evaluation compares against.
    - ``heading``: section-aware. A section that fits the budget stays whole (so a heading
      never gets separated from its body), a longer section is split further by length.

    Every chunk records the note offsets it came from, so a citation built from
    ``content`` can always be located in the note text.
    """

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        *,
        strategy: str = "char",
    ):
        if strategy not in STRATEGIES:
            raise ValueError(f"strategy must be one of {STRATEGIES}")
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._strategy = strategy
        # add_start_index 让切分器自己给出每块的起点，避免事后靠字符串搜索猜偏移。
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],
            add_start_index=True,
        )

    def describe(self) -> str:
        """Stable one-line descriptor, used to fingerprint an index configuration."""
        return f"{self._strategy}:{self._chunk_size}/{self._chunk_overlap}"

    def split(self, content: str) -> list[str]:
        """Return ordered chunk texts. Compatibility entry point."""
        return [chunk.content for chunk in self.split_with_metadata(content)]

    def split_with_metadata(self, content: str) -> list[NoteChunk]:
        """Return ordered chunks with their heading path and note offsets."""
        if not content:
            return []
        if self._strategy == "heading":
            return self._split_by_section(content)
        headings = note_headings(content)
        return [
            NoteChunk(
                content=piece,
                heading_path=heading_path_at(headings, start),
                start_char=start,
                end_char=start + len(piece),
            )
            for piece, start in self._split_offsets(content)
        ]

    def _split_by_section(self, content: str) -> list[NoteChunk]:
        """One chunk per short section; longer sections fall back to length splitting."""
        headings = note_headings(content)
        chunks: list[NoteChunk] = []
        for start, end, path in self._sections(content, headings):
            section = content[start:end]
            if len(section) <= self._chunk_size:
                chunks.append(
                    NoteChunk(
                        content=section,
                        heading_path=path,
                        start_char=start,
                        end_char=end,
                    )
                )
                continue
            for piece, local_start in self._split_offsets(section):
                absolute = start + local_start
                chunks.append(
                    NoteChunk(
                        content=piece,
                        heading_path=path,
                        start_char=absolute,
                        end_char=absolute + len(piece),
                    )
                )
        return chunks

    @staticmethod
    def _sections(
        content: str, headings: tuple
    ) -> list[tuple[int, int, str]]:
        """Split the note into (start, end, heading_path) sections.

        A section that holds nothing but its own heading line is dropped: it would
        otherwise become a handful of characters carrying no answerable content.
        """
        if not headings:
            return [(0, len(content), "")]
        sections: list[tuple[int, int, str]] = []
        if headings[0].start > 0:
            sections.append((0, headings[0].start, ""))
        for index, heading in enumerate(headings):
            end = headings[index + 1].start if index + 1 < len(headings) else len(content)
            body = content[heading.end : end]
            if not body.strip():
                continue
            sections.append((heading.start, end, heading.path))
        return sections

    def _split_offsets(self, text: str) -> list[tuple[str, int]]:
        """Length-based split plus each piece's verified offset inside ``text``."""
        pieces: list[tuple[str, int]] = []
        for document in self._splitter.create_documents([text]):
            piece = document.page_content
            start = int(document.metadata.get("start_index", -1))
            if start < 0 or text[start : start + len(piece)] != piece:
                raise ValueError(
                    "chunker produced a piece that is not a contiguous slice of the note; "
                    f"offset looked up as {start}"
                )
            pieces.append((piece, start))
        return pieces
