"""PDF local text extraction with vision fallback for textless pages."""
from io import BytesIO

from pypdf import PdfReader
import pypdfium2 as pdfium

from NoteAgent.BusinessModules.SourceFiles.SourceFileContracts import MAX_PAGES, MAX_PIXELS, ParsedFragment, ParseError, Vision
from NoteAgent.BusinessModules.SourceFiles.ImageFileParser import parse_image


def parse_pdf(data: bytes, vision: Vision | None, *, max_pages: int = MAX_PAGES,
              max_pixels: int = MAX_PIXELS) -> list[ParsedFragment]:
    parts: list[ParsedFragment] = []
    try:
        reader = PdfReader(BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise ParseError("加密 PDF 不支持")
        if len(reader.pages) > max_pages:
            raise ParseError("PDF 超过 100 页")
        for index, page in enumerate(reader.pages, 1):
            value = (page.extract_text() or "").strip()
            if not value:
                if vision is None:
                    raise ParseError(f"第 {index} 页需要已标记 vision 的模型配置")
                rendered = pdfium.PdfDocument(data)[index - 1].render(scale=1.5).to_pil()
                if rendered.width * rendered.height > max_pixels:
                    raise ParseError("PDF 页面超过 1600 万像素")
                stream = BytesIO()
                rendered.save(stream, format="PNG")
                value = parse_image(stream.getvalue(), "image/png", vision, max_pixels)
            parts.append(ParsedFragment(f"page {index}", value))
    except ParseError:
        raise
    except Exception as exc:
        raise ParseError("PDF 损坏或不可读取") from exc
    return parts
