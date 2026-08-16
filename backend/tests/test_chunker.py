from services.chunker import chunk, chunk_fixed, chunk_heading, chunk_semantic, heading_path, strip_boilerplate

import pytest

FIXTURE = """# Intro

Alpha sentence one. Beta sentence two. Gamma sentence three.

## Section A

Delta paragraph. Epsilon paragraph with more words.

### Subsection

Zeta detail. Eta detail continues.

## Section B

Final words here. Wrapping it up."""


def test_fixed_has_overlap():
    chunks = chunk_fixed(FIXTURE, max_tokens=30, overlap=0.1)
    assert len(chunks) > 1
    # second chunk should start before the first chunk ends (overlap)
    assert chunks[1].start < chunks[0].end


def test_fixed_token_budget_respected():
    chunks = chunk_fixed(FIXTURE, max_tokens=20, overlap=0.0)
    assert all(c.token_count <= 20 for c in chunks)


def test_semantic_keeps_boundaries():
    chunks = chunk_semantic(FIXTURE, max_tokens=30)
    assert chunks
    assert all(c.content.strip() for c in chunks)


def test_heading_preserves_headings():
    chunks = chunk_heading(FIXTURE, max_tokens=200)
    joined = "\n".join(c.content for c in chunks)
    assert "# Intro" in joined
    assert "## Section A" in joined
    assert "### Subsection" in joined


def test_chunk_dispatch_heading():
    chunks = chunk(FIXTURE, mode="heading", max_tokens=200)
    assert len(chunks) == 4  # 4 headings


def test_empty_input():
    assert chunk("", mode="fixed") == []
    assert chunk("", mode="semantic") == []
    assert chunk("", mode="heading") == []


URL_TEXT = (
    "# Guide\n\n"
    "See [Claude subscription](https://claude.com/pricing?utm_source=x&utm_medium=y) "
    "or the [Docs](https://docs.example.com/a.b/c). Account. Next sentence here.\n\n"
    "## Install\n\n"
    "```\ncurl -fsSL https://claude.ai/install.sh | bash\n```\n\n"
    "Then run `claude` in your project. It works great.\n"
)


def _assert_lossless(chunks, text):
    for c in chunks:
        assert c.content == text[c.start : c.end]
    assert sum(len(c.content) for c in chunks) == len(text)


@pytest.mark.parametrize("mode", ["fixed", "heading"])
def test_chunking_is_lossless_for_urls_and_code(mode):
    _assert_lossless(chunk(URL_TEXT, mode=mode, max_tokens=30), URL_TEXT)


def test_semantic_preserves_all_content():
    chunks = chunk(URL_TEXT, mode="semantic", max_tokens=30)
    joined = "\n".join(c.content for c in chunks)
    stripped = "".join(joined.split())
    expected = "".join(URL_TEXT.split())
    assert stripped == expected


def test_urls_not_split_across_sentences():
    chunks = chunk(URL_TEXT, mode="semantic", max_tokens=30)
    joined = "\n".join(c.content for c in chunks)
    assert "https://claude.com/pricing" in joined
    assert "https://docs.example.com/a.b/c" in joined


def test_code_blocks_not_split_mid_command():
    chunks = chunk(URL_TEXT, mode="heading", max_tokens=512)
    joined = "\n".join(c.content for c in chunks)
    assert "curl -fsSL https://claude.ai/install.sh | bash" in joined


def test_heading_includes_preamble():
    chunks = chunk(URL_TEXT, mode="heading", max_tokens=512)
    assert any("# Guide" in c.content for c in chunks)


def test_strip_boilerplate_removes_repeats_keeps_headers():
    markdown = (
        "# Install\n\n"
        "Run this one command.\n\n"
        "Run this one command.\n\n"
        "Run this one command.\n\n"
        "Run this one command.\n\n"
        "Run this one command.\n\n"
        "Run this one command.\n\n"
        "## Configure\n\n"
        "Set the key here.\n"
    )
    cleaned = strip_boilerplate(markdown)
    assert cleaned.count("Run this one command.") == 0
    assert "# Install" in cleaned
    assert "## Configure" in cleaned
    assert "Set the key here." in cleaned


def test_strip_boilerplate_keeps_rare_lines():
    markdown = (
        "# Install\n\n"
        "First unique sentence.\n\n"
        "Second unique sentence.\n"
    )
    cleaned = strip_boilerplate(markdown)
    assert "First unique sentence." in cleaned
    assert "Second unique sentence." in cleaned


def test_heading_path_returns_section():
    assert heading_path("## Setup\nSome text") == "## Setup"
    assert heading_path("preamble text only") == ""
    assert heading_path("### Deep\nmore") == "### Deep"
