from __future__ import annotations

from dataclasses import dataclass

import tiktoken

_ENCODINGS = ("cl100k_base", "o200k_base")


@dataclass(frozen=True)
class TokenStats:
    """Token and text metrics for a single document."""

    characters: int
    words: int
    tokens_cl100k: int
    tokens_o200k: int
    encodings: tuple[str, ...] = _ENCODINGS


def count_tokens(text: str, encoding: str = "cl100k_base") -> int:
    """Return the exact token count of `text` for `encoding`."""
    enc = tiktoken.get_encoding(encoding)
    return len(enc.encode(text))


def compute_stats(text: str) -> TokenStats:
    """Compute character, word, and dual-encoding token metrics for `text`."""
    return TokenStats(
        characters=len(text),
        words=len(text.split()),
        tokens_cl100k=count_tokens(text, "cl100k_base"),
        tokens_o200k=count_tokens(text, "o200k_base"),
    )