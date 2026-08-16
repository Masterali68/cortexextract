from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from services.token_counter import count_tokens

_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")
_SENTENCE_END = re.compile(r"[.!?]+(?=\s|$)")
_FENCE_RE = re.compile(r"```.+?```", re.DOTALL)
_CODE_SPAN_RE = re.compile(r"`[^`\n]*`")


@dataclass(frozen=True)
class Chunk:
    """A single chunk with char offsets and exact token count (cl100k_base)."""

    content: str
    start: int
    end: int
    token_count: int


def _iter_paragraphs(text: str):
    start = 0
    for match in _PARAGRAPH_SPLIT.finditer(text):
        yield text[start : match.start()], start
        start = match.end()
    if start < len(text):
        yield text[start:], start


def _protected_ranges(text: str) -> list[tuple[int, int]]:
    """Code spans + fenced code blocks, inside which we never split sentences."""
    ranges = [(m.start(), m.end()) for m in _FENCE_RE.finditer(text)]
    ranges += [(m.start(), m.end()) for m in _CODE_SPAN_RE.finditer(text)]
    ranges.sort()
    return ranges


def _in_ranges(pos: int, ranges: list[tuple[int, int]]) -> bool:
    for start, end in ranges:
        if start <= pos < end:
            return True
        if start > pos:
            break
    return False


def _iter_sentences(text: str):
    """Yield contiguous, lossless sentence segments.

    Splits only after sentence-ending punctuation that is directly followed by
    whitespace or end-of-string. Periods inside URLs (``claude.com``) and code
    spans are never boundaries, so the concatenation of yielded segments always
    reconstructs ``text`` exactly and no content is ever skipped.
    """
    ranges = _protected_ranges(text)
    start = 0
    for match in _SENTENCE_END.finditer(text):
        if _in_ranges(match.start(), ranges):
            continue
        yield text[start : match.end()], start
        start = match.end()
    if start < len(text):
        yield text[start:], start


def _greedy_fill(units, max_tokens: int):
    """Greedily pack `units` (text, offset) into token-budgeted chunks.

    Returns list of (content, start, end). Units never split mid-boundary.
    """
    packed: list[tuple[str, int, int]] = []
    i = 0
    while i < len(units):
        content = units[i][0]
        start = units[i][1]
        j = i + 1
        while j < len(units):
            candidate = content + units[j][0]
            if count_tokens(candidate) > max_tokens:
                break
            content = candidate
            j += 1
        end = units[j - 1][1] + len(units[j - 1][0]) if j > i else start + len(content)
        packed.append((content, start, end))
        i = j
    return packed


def chunk_fixed(text: str, max_tokens: int = 512, overlap: float = 0.1) -> list[Chunk]:
    """Mode 1: fixed token window with proportional token overlap."""
    sentences = list(_iter_sentences(text))
    if not sentences:
        return []

    chunks: list[tuple[str, int, int]] = []
    i = 0
    while i < len(sentences):
        content = sentences[i][0]
        start = sentences[i][1]
        j = i + 1
        while j < len(sentences):
            candidate = content + sentences[j][0]
            if count_tokens(candidate) > max_tokens:
                break
            content = candidate
            j += 1
        end = sentences[j - 1][1] + len(sentences[j - 1][0])
        chunks.append((content, start, end))

        tokens_used = count_tokens(content)
        overlap_target = int(tokens_used * overlap)
        acc = 0
        k = i
        while k < j and acc < overlap_target:
            acc += count_tokens(sentences[k][0])
            k += 1
        i = k if k > i else j

    return [Chunk(c, s, e, count_tokens(c)) for c, s, e in chunks]


def chunk_semantic(text: str, max_tokens: int = 512) -> list[Chunk]:
    """Mode 2: paragraph-first, sentence-second splitting on context boundaries."""
    chunks: list[tuple[str, int, int]] = []
    for paragraph, p_start in _iter_paragraphs(text):
        if count_tokens(paragraph) <= max_tokens:
            chunks.append((paragraph, p_start, p_start + len(paragraph)))
            continue
        sentences = list(_iter_sentences(paragraph))
        for content, s_start, s_end in _greedy_fill(sentences, max_tokens):
            chunks.append((content, p_start + s_start, p_start + s_end))
    return [Chunk(c, s, e, count_tokens(c)) for c, s, e in chunks]


def chunk_heading(text: str, max_tokens: int = 512) -> list[Chunk]:
    """Mode 3: structural markdown heading splitter (#, ##, ###)."""
    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        return chunk_semantic(text, max_tokens)

    sections: list[tuple[str, int]] = []
    first = matches[0].start()
    if first > 0 and text[:first].strip():
        sections.append((text[:first], 0))
    for idx, match in enumerate(matches):
        section_start = match.start()
        section_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        sections.append((text[section_start:section_end], section_start))

    chunks: list[tuple[str, int, int]] = []
    for section, s_start in sections:
        if count_tokens(section) <= max_tokens:
            chunks.append((section, s_start, s_start + len(section)))
            continue
        sentences = list(_iter_sentences(section))
        for content, s_off, s_end in _greedy_fill(sentences, max_tokens):
            chunks.append((content, s_start + s_off, s_start + s_end))
    return [Chunk(c, s, e, count_tokens(c)) for c, s, e in chunks]


def chunk(text: str, mode: str = "fixed", max_tokens: int = 512, overlap: float = 0.1) -> list[Chunk]:
    """Dispatch to the requested chunking mode."""
    if mode == "semantic":
        return chunk_semantic(text, max_tokens)
    if mode == "heading":
        return chunk_heading(text, max_tokens)
    return chunk_fixed(text, max_tokens, overlap)


def strip_boilerplate(markdown: str, max_occurrences: int = 5) -> str:
    """Remove repeated boilerplate lines (nav/footer/prev-next leaks) before
    vector storage so retrieval is not polluted by near-identical junk.

    Headings and blank lines are always kept. A non-empty, non-heading line
    whose stripped form appears more than `max_occurrences` times is dropped.
    Applied to the vector-store copy only; the editor markdown stays lossless.
    """
    lines = markdown.split("\n")
    counts = Counter(line.strip() for line in lines if line.strip())
    kept = [
        line
        for line in lines
        if not line.strip()
        or line.lstrip().startswith("#")
        or counts.get(line.strip(), 0) <= max_occurrences
    ]
    return "\n".join(kept).strip() + "\n"


def heading_path(content: str) -> str:
    """Return the first markdown heading line in a chunk (its section), for
    section-aware retrieval metadata. Empty string when the chunk is preamble."""
    for line in content.split("\n"):
        if re.match(r"^#{1,6}\s+", line):
            return line.strip()
    return ""