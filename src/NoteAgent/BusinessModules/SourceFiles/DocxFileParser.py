"""DOCX paragraph/table extraction in document-body order."""
from io import BytesIO

from docx import Document
from docx.oxml.ns import qn

from NoteAgent.BusinessModules.SourceFiles.SourceFileContracts import ParsedFragment, ParseError


def parse_docx(data: bytes) -> list[ParsedFragment]:
    parts: list[ParsedFragment] = []
    try:
        doc = Document(BytesIO(data))
        for index, child in enumerate(doc.element.body.iterchildren(), 1):
            if child.tag == qn("w:p"):
                value = "".join(node.text or "" for node in child.iter(qn("w:t")))
            elif child.tag == qn("w:tbl"):
                rows = []
                for row in child.iter(qn("w:tr")):
                    cells = ["".join(node.text or "" for node in cell.iter(qn("w:t")))
                             for cell in row.iter(qn("w:tc"))]
                    rows.append(" | ".join(cells))
                value = "\n".join(rows)
            else:
                continue
            if value.strip():
                parts.append(ParsedFragment(f"block {index}", value.strip()))
    except Exception as exc:
        raise ParseError("DOCX 损坏或不可读取") from exc
    return parts
