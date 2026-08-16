from services.token_counter import compute_stats, count_tokens


def test_count_tokens_cl100k():
    assert count_tokens("hello world", "cl100k_base") == 2
    assert count_tokens("", "cl100k_base") == 0


def test_count_tokens_encodings():
    text = "The quick brown fox jumps over the lazy dog."
    assert count_tokens(text, "cl100k_base") > 0
    assert count_tokens(text, "o200k_base") > 0


def test_compute_stats_fields():
    stats = compute_stats("one two three")
    assert stats.characters == len("one two three")
    assert stats.words == 3
    assert stats.tokens_cl100k == stats.tokens_o200k  # short ASCII is stable
