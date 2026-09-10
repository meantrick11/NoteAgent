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


def test_sanitize_renumbers_used_in_appearance_order():
    registry = CitationRegistry()
    registry.register(file_name="A.md", chunk_index=0, quote="a")
    registry.register(file_name="B.md", chunk_index=1, quote="b")
    registry.register(file_name="C.md", chunk_index=2, quote="c")
    text, used = sanitize_answer("先[[cite:3]]再[[cite:2]]尾", registry)
    assert text == "先[[cite:1]]再[[cite:2]]尾"
    assert used == [
        {"index": 1, "file_name": "C.md", "chunk_index": 2, "quote": "c"},
        {"index": 2, "file_name": "B.md", "chunk_index": 1, "quote": "b"},
    ]


def test_sanitize_reuses_display_index_for_repeat_cite():
    registry = CitationRegistry()
    registry.register(file_name="A.md", chunk_index=0, quote="a")
    registry.register(file_name="B.md", chunk_index=1, quote="b")
    text, used = sanitize_answer("[[cite:2]] and [[cite:2]]", registry)
    assert text == "[[cite:1]] and [[cite:1]]"
    assert used == [
        {"index": 1, "file_name": "B.md", "chunk_index": 1, "quote": "b"},
    ]


def test_strip_cite_markers():
    assert strip_cite_markers("a[[cite:1]]b[[cite:2]]c") == "abc"
