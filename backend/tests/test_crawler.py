import asyncio

import pytest

from schemas import CrawlRequest
from services.crawler import (
    _index_candidates,
    _is_markdown_url,
    _markdown_title,
    _parse_llms_txt,
    _parse_sitemap,
    crawl_site,
    discover_index_urls,
    is_ignorable,
    normalize_url,
    same_host,
)
from services.scraper import ScrapeResult


def test_normalize_url():
    assert normalize_url("HTTPS://Example.com:443/Path?A=1&b=2#frag") == "https://example.com/Path?A=1&b=2"
    assert normalize_url("http://example.com:80/x") == "http://example.com/x"
    assert normalize_url("http://example.com:8080/x") == "http://example.com:8080/x"
    assert normalize_url("https://example.com") == "https://example.com/"
    assert normalize_url("not a url") == ""


def test_same_host():
    assert same_host("https://example.com/a", "https://example.com/b")
    assert same_host("https://example.com/a", "https://sub.example.com/b") is False
    assert same_host("https://example.com:8080/a", "https://example.com:8081/b") is False


def test_is_ignorable():
    assert is_ignorable("https://example.com/logo.png")
    assert is_ignorable("https://example.com/docs.zip")
    assert is_ignorable("https://example.com/video.mp4")
    assert is_ignorable("https://example.com/page.pdf")
    assert is_ignorable("https://example.com/docs/setup") is False
    assert is_ignorable("https://example.com/") is False


def test_crawl_request_defaults():
    request = CrawlRequest(url="https://example.com")
    assert request.max_pages == 25
    assert request.max_depth == 3
    assert request.chunk_mode == "heading"
    assert request.store_vectors is True
    with pytest.raises(Exception):
        CrawlRequest(url="")


async def _run_bfs():
    import services.crawler as crawler

    pages = {
        "https://example.com/": ScrapeResult(
            html="<h1>Home</h1><p>Home page body with enough text.</p>",
            final_url="https://example.com/",
            content_metadata={
                "content_score": 100,
                "discovered_links": [
                    "https://example.com/docs",
                    "https://example.com/logo.png",
                    "https://external.com/away",
                    "https://example.com/docs",
                ],
            },
        ),
        "https://example.com/docs": ScrapeResult(
            html="<h1>Docs</h1><p>Docs page body with enough text.</p>",
            final_url="https://example.com/docs",
            content_metadata={"content_score": 90, "discovered_links": []},
        ),
    }
    stored = []

    async def fake_scrape(url, render_js=True, timeout_seconds=30):
        if url not in pages:
            raise RuntimeError("unexpected page")
        return pages[url]

    async def fake_upsert(documents):
        stored.append(documents)
        return len(documents)

    async def fake_count():
        return sum(len(d) for d in stored)

    async def fake_embed(texts, provider="ollama", api_key="", endpoint=""):
        return [[0.0] * 8 for _ in texts]

    async def fake_ensure():
        return None

    crawler.scrape_page = fake_scrape
    crawler.vector_store.upsert_documents = fake_upsert
    crawler.vector_store.count_documents = fake_count
    crawler.vector_store.ensure_schema = fake_ensure
    crawler.embed_texts = fake_embed

    result = await crawl_site(
        "https://example.com/",
        max_pages=10,
        max_depth=2,
        store_vectors=True,
        use_index=False,
    )
    assert result["pages_crawled"] == 2
    assert result["chunks_stored"] >= 2
    assert result["total_documents"] >= 2
    assert len(result["failures"]) == 0
    urls = {p["url"] for p in result["pages"]}
    assert "https://example.com/" in urls
    assert "https://example.com/docs" in urls


def test_bfs_same_host_and_dedup():
    asyncio.run(_run_bfs())


async def _run_failures_not_fatal():
    import services.crawler as crawler

    calls = {"n": 0}

    async def flaky_scrape(url, render_js=True, timeout_seconds=30):
        calls["n"] += 1
        if url.endswith("/broken"):
            raise RuntimeError("network blip")
        return ScrapeResult(
            html="<h1>OK</h1><p>Recovered page with real content.</p>",
            final_url=url,
            content_metadata={"content_score": 60, "discovered_links": ["https://example.com/broken"]},
        )

    async def fake_ensure():
        return None

    async def fake_embed(texts, provider="ollama", api_key="", endpoint=""):
        return [[0.0] * 8 for _ in texts]

    crawler.scrape_page = flaky_scrape
    crawler.vector_store.ensure_schema = fake_ensure
    crawler.embed_texts = fake_embed

    result = await crawl_site(
        "https://example.com/",
        max_pages=10,
        max_depth=2,
        store_vectors=False,
        use_index=False,
    )
    assert len(result["failures"]) == 1
    assert result["pages_crawled"] == 1


def test_failures_not_fatal():
    asyncio.run(_run_failures_not_fatal())


def test_parse_llms_txt_extracts_markdown_links():
    text = (
        "# Docs\n"
        "> A curated index\n\n"
        "- [Setup](https://example.com/docs/setup)\n"
        "- [API Reference](https://example.com/docs/api)\n"
        "- [relative](/docs/relative) should be ignored\n"
        "Plain prose with a link https://example.com/naked is also skipped.\n"
    )
    urls = _parse_llms_txt(text)
    assert urls == ["https://example.com/docs/setup", "https://example.com/docs/api"]


def test_parse_sitemap_extracts_locs():
    text = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        "  <url><loc>https://example.com/</loc></url>\n"
        "  <url><loc>https://example.com/docs/api</loc></url>\n"
        "  <url><loc>/relative/only</loc></url>\n"
        "</urlset>\n"
    )
    assert _parse_sitemap(text) == ["https://example.com/", "https://example.com/docs/api"]


def test_index_candidates_climb_the_seed_path():
    candidates = _index_candidates("https://example.com/docs/en/overview")
    assert "https://example.com/docs/en/llms.txt" in candidates
    assert "https://example.com/docs/llms.txt" in candidates
    assert "https://example.com/llms.txt" in candidates
    assert "https://example.com/sitemap.xml" in candidates


def test_discover_index_prefers_llms_over_sitemap():
    import services.crawler as crawler

    async def fake_fetch(session, url, timeout):
        if "llms.txt" in url and url.endswith("/docs/llms.txt"):
            return "- [Setup](https://example.com/docs/setup)\n"
        if "sitemap.xml" in url:
            return "<url><loc>https://example.com/docs/api</loc></url>\n"
        return None

    crawler._fetch_text = fake_fetch
    index_url, kind, urls = asyncio.run(
        crawler.discover_index_urls("https://example.com/docs/en/overview", None)
    )
    assert kind == "llms"
    assert index_url == "https://example.com/docs/llms.txt"
    assert urls == ["https://example.com/docs/setup", "https://example.com/docs/api"]


def test_discover_index_returns_none_when_absent():
    import services.crawler as crawler

    async def fake_fetch(session, url, timeout):
        return None

    crawler._fetch_text = fake_fetch
    index_url, kind, urls = asyncio.run(
        crawler.discover_index_urls("https://example.com/docs/en/overview", None)
    )
    assert index_url is None
    assert kind is None
    assert urls == []


def test_discover_index_requires_a_host():
    index_url, kind, urls = asyncio.run(
        discover_index_urls("not a url", None)
    )
    assert index_url is None
    assert urls == []


async def _run_index_seeded_crawl():
    import services.crawler as crawler

    pages = {
        "https://example.com/": ScrapeResult(
            html="<h1>Home</h1><p>Home page body with enough text.</p>",
            final_url="https://example.com/",
            content_metadata={"content_score": 100, "discovered_links": []},
        ),
        "https://example.com/docs/setup": ScrapeResult(
            html="<h1>Setup</h1><p>Setup page body with enough text.</p>",
            final_url="https://example.com/docs/setup",
            content_metadata={
                "content_score": 90,
                "discovered_links": ["https://example.com/docs/deep"],
            },
        ),
        "https://example.com/docs/api": ScrapeResult(
            html="<h1>API</h1><p>API page body with enough text.</p>",
            final_url="https://example.com/docs/api",
            content_metadata={"content_score": 80, "discovered_links": []},
        ),
        "https://example.com/docs/deep": ScrapeResult(
            html="<h1>Deep</h1><p>Deep page body with enough text.</p>",
            final_url="https://example.com/docs/deep",
            content_metadata={"content_score": 70, "discovered_links": []},
        ),
    }

    async def fake_scrape(url, render_js=True, timeout_seconds=30):
        if url not in pages:
            raise RuntimeError(f"unexpected page: {url}")
        return pages[url]

    async def fake_discover(seed_url, session, timeout=8.0):
        return (
            "https://example.com/llms.txt",
            "llms",
            [
                "https://example.com/docs/setup",
                "https://example.com/docs/api",
                "https://external.com/away",
            ],
        )

    crawler.scrape_page = fake_scrape
    crawler.discover_index_urls = fake_discover

    result = await crawl_site(
        "https://example.com/",
        max_pages=4,
        max_depth=2,
        store_vectors=False,
    )
    assert result["strategy"] == "index:llms"
    assert result["index_used"] == "https://example.com/llms.txt"
    assert result["pages_crawled"] == 4
    by_url = {p["url"]: p["via"] for p in result["pages"]}
    assert by_url["https://example.com/"] == "seed"
    assert by_url["https://example.com/docs/setup"] == "index"
    assert by_url["https://example.com/docs/api"] == "index"
    assert by_url["https://example.com/docs/deep"] == "link"
    assert "https://external.com/away" not in by_url
    # Index order is preserved (llms.txt order = curated importance), not set order.
    assert [p["url"] for p in result["pages"]] == [
        "https://example.com/",
        "https://example.com/docs/setup",
        "https://example.com/docs/api",
        "https://example.com/docs/deep",
    ]


def test_crawl_uses_index_seeds():
    asyncio.run(_run_index_seeded_crawl())


def test_is_markdown_url():
    assert _is_markdown_url("https://example.com/docs/setup.md")
    assert _is_markdown_url("https://example.com/docs/setup.MD")
    assert _is_markdown_url("https://example.com/docs/guide.markdown")
    assert _is_markdown_url("https://example.com/docs/en/overview.md?utm=1")
    assert _is_markdown_url("https://example.com/docs/setup") is False
    assert _is_markdown_url("https://example.com/docs/setup.html") is False


def test_markdown_title_from_heading():
    assert _markdown_title("# Overview\n\nSome text") == "Overview"
    assert _markdown_title("## [Deep](x) Link\nbody") == "[Deep](x) Link"
    assert _markdown_title("plain first line\nmore") == "plain first line"
    assert _markdown_title("") == ""


async def _run_markdown_crawl():
    import services.crawler as crawler

    html_pages = {
        "https://example.com/": ScrapeResult(
            html="<h1>Home</h1><p>Home page body with enough text.</p>",
            final_url="https://example.com/",
            content_metadata={"content_score": 100, "discovered_links": []},
        ),
    }
    markdown_pages = {
        "https://example.com/docs/setup.md": "# Setup\n\nFollow the setup guide.\n\n- [API](https://example.com/docs/api.md)\n",
        "https://example.com/docs/api.md": "# API\n\nAPI reference body.\n",
    }

    async def fake_scrape(url, render_js=True, timeout_seconds=30):
        if url not in html_pages:
            raise RuntimeError(f"unexpected html page: {url}")
        return html_pages[url]

    async def fake_fetch_markdown(session, url, timeout):
        return markdown_pages.get(url)

    async def fake_discover(seed_url, session, timeout=8.0):
        return (
            "https://example.com/llms.txt",
            "llms",
            ["https://example.com/docs/setup.md"],
        )

    async def fake_ensure():
        return None

    async def fake_embed(texts, provider="ollama", api_key="", endpoint=""):
        return [[0.0] * 8 for _ in texts]

    async def fake_upsert(documents):
        return len(documents)

    async def fake_count():
        return 99

    scraper_calls = {"n": 0}
    original_scrape = crawler.scrape_page

    async def tracking_scrape(url, render_js=True, timeout_seconds=30):
        scraper_calls["n"] += 1
        return await original_scrape(url, render_js=render_js, timeout_seconds=timeout_seconds)

    crawler.scrape_page = tracking_scrape
    crawler._fetch_markdown = fake_fetch_markdown
    crawler.discover_index_urls = fake_discover
    crawler.vector_store.ensure_schema = fake_ensure
    crawler.vector_store.upsert_documents = fake_upsert
    crawler.vector_store.count_documents = fake_count
    crawler.embed_texts = fake_embed

    try:
        result = await crawl_site(
            "https://example.com/",
            max_pages=4,
            max_depth=2,
            store_vectors=True,
        )
    finally:
        crawler.scrape_page = original_scrape

    assert result["strategy"] == "index:llms"
    assert result["pages_crawled"] == 3
    by_url = {p["url"]: p for p in result["pages"]}
    assert by_url["https://example.com/docs/setup.md"]["title"] == "Setup"
    assert by_url["https://example.com/docs/setup.md"]["via"] == "index"
    # Markdown pages must be fetched directly, never rendered by Playwright.
    assert scraper_calls["n"] == 1
    # The markdown link [API] was discovered and link-followed.
    assert by_url["https://example.com/docs/api.md"]["via"] == "link"
    # setup.md's content was embedded and stored as chunks.
    assert by_url["https://example.com/docs/setup.md"]["chunks_stored"] > 0


def test_crawl_uses_markdown_direct():
    asyncio.run(_run_markdown_crawl())