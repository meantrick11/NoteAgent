from noteagent.chat.context_tokens import estimate_tokens, prefix_until_tokens


def test_empty_is_zero():
    assert estimate_tokens("") == 0


def test_four_chars_is_one():
    assert estimate_tokens("abcd") == 1


def test_five_chars_is_two():
    assert estimate_tokens("abcde") == 2  # (5+3)//4 == 2


def test_prefix_fits_unchanged():
    assert prefix_until_tokens("hello", 2) == ("hello", False)


def test_prefix_truncates_by_token():
    prefix, truncated = prefix_until_tokens("x" * 200, 2)
    assert truncated is True
    assert estimate_tokens(prefix) <= 2


def test_prefix_zero_tokens_returns_empty():
    assert prefix_until_tokens("abc", 0) == ("", True)
    assert prefix_until_tokens("", 0) == ("", False)
