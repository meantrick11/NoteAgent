from langchain_text_splitters import RecursiveCharacterTextSplitter


class MarkdownChunker:
    """Split Markdown into overlapping character chunks, preferring Chinese punctuation."""

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],
        )

    def split(self, content: str) -> list[str]:
        """Return ordered text chunks for embedding."""
        return self._splitter.split_text(content)
