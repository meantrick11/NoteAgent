"""UTF-8 plain-text and Markdown extraction."""
from NoteAgent.Modules.Sources.Domain.Vo.SourceFileContracts import ParsedFragment, ParseError


def parse_text(data: bytes) -> list[ParsedFragment]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ParseError("文本文件需要 UTF-8 编码") from exc
    return [ParsedFragment(f"paragraph {index}", paragraph.strip())
            for index, paragraph in enumerate(text.split("\n\n"), 1) if paragraph.strip()]
