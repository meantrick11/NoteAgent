from noteagent.retrieval.chunker import MarkdownChunker


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
