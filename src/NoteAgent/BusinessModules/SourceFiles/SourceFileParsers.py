"""Dispatch format parsers and publish only complete bounded extraction."""
from NoteAgent.BusinessModules.SourceFiles.SourceFileContracts import (
    MAX_CHARACTERS, MAX_PAGES, MAX_PIXELS, ParsedFragment, ParseError, Vision,
)
from NoteAgent.BusinessModules.SourceFiles.TextFileParser import parse_text
from NoteAgent.BusinessModules.SourceFiles.DocxFileParser import parse_docx
from NoteAgent.BusinessModules.SourceFiles.PdfFileParser import parse_pdf
from NoteAgent.BusinessModules.SourceFiles.ImageFileParser import parse_image


def parse_source(
    media_type: str, data: bytes, *, vision: Vision | None = None,
    max_pages: int = MAX_PAGES, max_pixels: int = MAX_PIXELS,
    max_characters: int = MAX_CHARACTERS,
) -> list[ParsedFragment]:
    if media_type in ("text/plain", "text/markdown"):
        parts = parse_text(data)
    elif media_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        parts = parse_docx(data)
    elif media_type == "application/pdf":
        parts = parse_pdf(data, vision, max_pages=max_pages, max_pixels=max_pixels)
    elif media_type in ("image/png", "image/jpeg"):
        parts = [ParsedFragment("image 1", parse_image(data, media_type, vision, max_pixels))]
    else:
        raise ParseError("不支持的文件格式")
    if not parts or not any(part.text.strip() for part in parts):
        raise ParseError("文件没有可用内容")
    if sum(len(part.text) for part in parts) > max_characters:
        raise ParseError("解析文本超过 20 万字符")
    return parts
