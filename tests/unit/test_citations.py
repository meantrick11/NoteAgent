from noteagent.chat.citations import CitationRegistry, sanitize_answer, strip_cite_markers


def test_register_reuses_same_chunk():
    registry = CitationRegistry()
    a = registry.register(file_name="Go.md", chunk_index=0, quote="hello")
    b = registry.register(file_name="Go.md", chunk_index=0, quote="hello")
    c = registry.register(file_name="Go.md", chunk_index=1, quote="other")
    assert a == b == 1
    assert c == 2


def test_read_source_has_no_quote():
    registry = CitationRegistry()
    n = registry.register(file_name="Lang/Go.md")
    cite = registry.get(n)
    assert cite is not None
    assert cite.chunk_index is None
    assert cite.quote is None


def test_sanitize_keeps_valid_drops_unknown():
    registry = CitationRegistry()
    registry.register(file_name="A.md", chunk_index=0, quote="q")
    text, used = sanitize_answer("事实[[cite:1]] 假[[cite:9]]尾", registry)
    assert text == "事实[[cite:1]] 假尾"
    assert used == [
        {"index": 1, "file_name": "A.md", "chunk_index": 0, "quote": "q"},
    ]


def test_strip_cite_markers():
    assert strip_cite_markers("a[[cite:1]]b[[cite:2]]c") == "abc"
