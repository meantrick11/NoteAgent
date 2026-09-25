from noteagent.retrieval.chunker import MarkdownChunker
from noteagent.retrieval.models import NoteChunk

FENCED_NOTE = """# 3. Python 速览

## 3.1. 计算器

看这个例子：

```python
# 这是第一条注释
2 + 2
```

正文继续。

## 3.2. 下一步

- 一个要点
"""


def test_chunker_keeps_short_text_together():
    chunker = MarkdownChunker(chunk_size=500, chunk_overlap=50)
    text = "第一段。\n\n第二段。"
    assert chunker.split(text) == [text]


def test_chunker_splits_long_text():
    chunker = MarkdownChunker(chunk_size=40, chunk_overlap=0)
    paragraph = "这是一段用于测试切块的中文内容，需要足够长才会被拆开。"
    text = f"{paragraph}\n\n{paragraph}\n\n{paragraph}"
    chunks = chunker.split(text)
    assert len(chunks) >= 2


# --- 章节感知切块：以下用例都来自语料里真实出现过的失败 -------------------------


def test_split_stays_a_compatible_entry_point():
    chunker = MarkdownChunker(chunk_size=120, chunk_overlap=0, strategy="heading")
    content = FENCED_NOTE
    assert chunker.split(content) == [
        chunk.content for chunk in chunker.split_with_metadata(content)
    ]


def test_every_chunk_maps_back_to_the_note_text():
    for strategy in ("char", "heading"):
        chunker = MarkdownChunker(chunk_size=120, chunk_overlap=20, strategy=strategy)
        for chunk in chunker.split_with_metadata(FENCED_NOTE):
            assert FENCED_NOTE[chunk.start_char : chunk.end_char] == chunk.content


def test_hash_comment_inside_a_code_fence_is_not_a_heading():
    # Python_Tutorial_Overview 里有 7 处这种注释，纯文本解析会把它们当成 H1。
    chunker = MarkdownChunker(chunk_size=500, chunk_overlap=0, strategy="heading")
    chunks = chunker.split_with_metadata(FENCED_NOTE)
    fence_chunks = [chunk for chunk in chunks if "# 这是第一条注释" in chunk.content]
    assert fence_chunks
    for chunk in fence_chunks:
        assert chunk.heading_path == "3. Python 速览 > 3.1. 计算器"


def test_a_short_section_keeps_its_heading_with_its_body():
    chunker = MarkdownChunker(chunk_size=500, chunk_overlap=0, strategy="heading")
    chunks = chunker.split_with_metadata(FENCED_NOTE)
    final = [chunk for chunk in chunks if "一个要点" in chunk.content]
    assert len(final) == 1
    assert "3.2. 下一步" in final[0].content
    assert final[0].heading_path == "3. Python 速览 > 3.2. 下一步"


def test_chunks_do_not_cross_a_section_boundary():
    chunker = MarkdownChunker(chunk_size=500, chunk_overlap=0, strategy="heading")
    for chunk in chunker.split_with_metadata(FENCED_NOTE):
        assert chunk.content.count("## ") <= 1


def test_a_long_section_is_split_and_keeps_one_heading_path():
    body = "很长的句子。" * 60
    content = f"# 根\n\n## 长章节\n\n{body}\n"
    chunker = MarkdownChunker(chunk_size=200, chunk_overlap=20, strategy="heading")
    chunks = chunker.split_with_metadata(content)
    assert len(chunks) >= 3
    assert {chunk.heading_path for chunk in chunks} == {"根 > 长章节"}
    for chunk in chunks:
        assert content[chunk.start_char : chunk.end_char] == chunk.content


def test_a_long_code_fence_is_split_without_losing_the_source_position():
    code = "\n".join(f"print({index})  # 第 {index} 行" for index in range(80))
    content = f"# 根\n\n## 代码\n\n```python\n{code}\n```\n"
    chunker = MarkdownChunker(chunk_size=200, chunk_overlap=0, strategy="heading")
    chunks = chunker.split_with_metadata(content)
    assert len(chunks) >= 3
    rebuilt = "".join(chunk.content for chunk in chunks)
    for line in code.splitlines():
        assert line in rebuilt
    for chunk in chunks:
        assert content[chunk.start_char : chunk.end_char] == chunk.content


def test_repeated_paragraphs_get_distinct_offsets():
    repeated = "完全相同的重复段落，必须映射到各自的偏移。"
    content = f"# 根\n\n## 第一节\n\n{repeated}\n\n## 第二节\n\n{repeated}\n"
    chunker = MarkdownChunker(chunk_size=500, chunk_overlap=0, strategy="heading")
    chunks = chunker.split_with_metadata(content)
    hits = [chunk for chunk in chunks if repeated in chunk.content]
    assert len(hits) == 2
    assert hits[0].start_char < hits[1].start_char
    assert hits[0].heading_path != hits[1].heading_path


def test_a_short_table_stays_with_its_header():
    table = "| 语法 | 状态 |\n| --- | --- |\n| RDF/XML | 必需 |\n| Turtle | 可选 |\n"
    content = f"# 根\n\n## 语法表\n\n{table}"
    chunker = MarkdownChunker(chunk_size=500, chunk_overlap=0, strategy="heading")
    chunks = chunker.split_with_metadata(content)
    assert len(chunks) == 1
    assert "| 语法 | 状态 |" in chunks[0].content
    assert "| Turtle | 可选 |" in chunks[0].content


def test_char_strategy_also_reports_offsets_and_heading_paths():
    chunker = MarkdownChunker(chunk_size=120, chunk_overlap=20, strategy="char")
    chunks: list[NoteChunk] = chunker.split_with_metadata(FENCED_NOTE)
    assert all(chunk.heading_path for chunk in chunks)
    assert chunks[0].start_char == 0


def test_describe_reports_the_configuration_for_index_fingerprints():
    char = MarkdownChunker(chunk_size=500, chunk_overlap=50, strategy="char")
    heading = MarkdownChunker(chunk_size=500, chunk_overlap=50, strategy="heading")
    assert char.describe() != heading.describe()
    assert "500" in char.describe()
