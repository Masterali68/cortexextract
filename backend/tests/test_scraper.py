import asyncio
import pytest

from services.scraper import (
    ScraperFallbackError,
    ScrapeResult,
    _discover_links,
    _score_html,
    scrape_page,
)


def test_score_html_counts_meaningful_text():
    rich = "<html><body><h1>Title</h1><p>Some meaningful paragraph text here.</p><script>var x;</script></body></html>"
    shell = "<html><body><div id='app'></div><script>window.__INITIAL__='x'</script></body></html>"
    assert _score_html(rich) > 40
    assert _score_html(shell) == 0


def test_discover_links_plain_and_js_buttons():
    html = """<html><body>
    <a href="/docs/setup">Docs</a>
    <a href="https://example.com/absolute">Abs</a>
    <button data-href="/install">Click here</button>
    <div role="button" data-url="https://example.com/download">Go</div>
    <button onclick="location.href='/pricing'">Price</button>
    <a onclick="window.open('/about')">About</a>
    <a href="#fragment">Skip</a>
    <a href="mailto:x@y.z">Mail</a>
    <a href="javascript:void(0)">JS</a>
    </body></html>"""
    links = _discover_links(html, "https://example.com/start")
    assert "https://example.com/docs/setup" in links
    assert "https://example.com/absolute" in links
    assert "https://example.com/install" in links
    assert "https://example.com/download" in links
    assert "https://example.com/pricing" in links
    assert "https://example.com/about" in links
    assert not any("mailto" in l or "javascript" in l or "#" in l for l in links)


def test_discover_links_filters_non_http():
    links = _discover_links('<a href="tel:123">Call</a><a href="ftp://x">F</a>', "https://a.com")
    assert links == []


async def _run_retry_then_static():
    calls = {"attempts": 0}

    async def flaky_dynamic(url, timeout_seconds, attempt=0):
        calls["attempts"] += 1
        raise ScraperFallbackError("challenge")

    async def static(url, timeout_seconds):
        return ScrapeResult(
            html="<h1>Static</h1><p>This is the static fallback tier serving real article content that reads well.</p>",
            final_url=url,
            source="static",
        )

    import services.scraper as scraper

    scraper._scrape_playwright = flaky_dynamic
    scraper._scrape_static = static

    result = await scrape_page("https://example.com")
    assert result.source == "static"
    assert calls["attempts"] == 3


def test_retry_rotation_then_static():
    asyncio.run(_run_retry_then_static())


async def _run_second_attempt():
    calls = {"attempts": 0}

    async def dynamic(url, timeout_seconds, attempt=0):
        calls["attempts"] += 1
        if attempt == 0:
            raise ScraperFallbackError("challenge")
        return ScrapeResult(html="<h1>OK</h1><p>This page rendered fine with several paragraphs of real content for testing.</p>", final_url=url)

    async def static(url, timeout_seconds):
        return ScrapeResult(html="<h1>Shell</h1>", final_url=url, source="static")

    import services.scraper as scraper

    scraper._scrape_playwright = dynamic
    scraper._scrape_static = static

    result = await scrape_page("https://example.com")
    assert result.source == "playwright"
    assert calls["attempts"] == 2


def test_succeeds_on_second_attempt():
    asyncio.run(_run_second_attempt())


async def _run_prefers_richer_tier():
    async def thin_dynamic(url, timeout_seconds, attempt=0):
        return ScrapeResult(html="<h1>T</h1><p>A short dynamic page body with a little content in it.</p>", final_url=url)

    async def rich_static(url, timeout_seconds):
        return ScrapeResult(
            html="<h1>Full</h1><p>This is a much longer server-rendered body that contains plenty of real readable content for scoring.</p>",
            final_url=url,
            source="static",
        )

    import services.scraper as scraper

    scraper._scrape_playwright = thin_dynamic
    scraper._scrape_static = rich_static

    result = await scrape_page("https://example.com")
    assert result.source == "static"
    assert result.content_metadata["tier_scores"]["static"] > result.content_metadata["tier_scores"]["playwright"]


def test_prefers_richer_tier():
    asyncio.run(_run_prefers_richer_tier())


async def _run_rejects_empty_shell():
    async def shell_dynamic(url, timeout_seconds, attempt=0):
        return ScrapeResult(
            html="<html><head><title>x</title></head><body><div id=app></div></body></html>",
            final_url=url,
        )

    async def shell_static(url, timeout_seconds):
        return ScrapeResult(
            html="<html><body><script>var x;</script></body></html>",
            final_url=url,
            source="static",
        )

    import services.scraper as scraper

    scraper._scrape_playwright = shell_dynamic
    scraper._scrape_static = shell_static

    with pytest.raises(ScraperFallbackError):
        await scrape_page("https://example.com")


def test_rejects_empty_shell():
    asyncio.run(_run_rejects_empty_shell())


async def _run_metadata_links_and_score():
    async def dynamic(url, timeout_seconds, attempt=0):
        return ScrapeResult(
            html="<h1>T</h1><p>Content page with a heading and a body paragraph for tests.</p><a href='/sub'>Sub</a><button data-href='/btn'>B</button>",
            final_url=url,
        )

    async def static(url, timeout_seconds):
        return ScrapeResult(html="<h1>t</h1><p>A shorter static page that still contains readable content.</p>", final_url=url, source="static")

    import services.scraper as scraper

    scraper._scrape_playwright = dynamic
    scraper._scrape_static = static

    result = await scrape_page("https://example.com")
    assert result.content_metadata["content_score"] > 0
    assert "https://example.com/sub" in result.content_metadata["discovered_links"]
    assert "https://example.com/btn" in result.content_metadata["discovered_links"]


def test_metadata_exposes_links_and_score():
    asyncio.run(_run_metadata_links_and_score())


async def _run_all_tiers_fail():
    async def bad_dynamic(url, timeout_seconds, attempt=0):
        raise ScraperFallbackError("challenge")

    async def bad_static(url, timeout_seconds):
        raise RuntimeError("network down")

    import services.scraper as scraper

    scraper._scrape_playwright = bad_dynamic
    scraper._scrape_static = bad_static

    with pytest.raises(ScraperFallbackError):
        await scrape_page("https://example.com")


def test_all_tiers_fail_raises():
    asyncio.run(_run_all_tiers_fail())
