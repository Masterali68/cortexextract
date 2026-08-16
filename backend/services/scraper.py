from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass, field
from random import choice
from typing import Optional
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
import trafilatura
from bs4 import BeautifulSoup
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

logger = logging.getLogger("cortexextract.scraper")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
]

_CHROMIUM_FLAGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-dev-shm-usage",
    "--no-sandbox",
    "--disable-gpu",
    "--disable-infobars",
]

_CLOUDFLARE_HINTS = (
    "cf-challenge",
    "challenge-platform",
    "just a moment",
    "enable javascript and cookies to continue",
    "__cf_chl_",
)

_PROXY_URLS = [
    url.strip()
    for url in os.getenv("PROXY_URLS", "").split(",")
    if url.strip()
]

_VIEWPORTS = [
    {"width": 1440, "height": 900},
    {"width": 1280, "height": 800},
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
]

_MAX_DYNAMIC_ATTEMPTS = 3
# Pages scoring below this many meaningful characters (headings + paragraphs
# + list items + code blocks, script/style stripped) are treated as empty
# shells (JS shell, CAPTCHA gate, bot wall) and rejected instead of stored.
_SHELL_MIN_SCORE = 60

_JS_LINK_ATTRS = ("data-href", "data-url", "data-target")
# onclick variants that reveal a navigation destination without clicking:
#   onclick="location.href='/x'" / "window.location='/x'" / "navigateTo('/x')"
_ONCLICK_URL_RE = re.compile(
    r"(?:window\.)?(?:location(?:\.href)?|location\.assign|location\.replace|"
    r"window\.open|navigate(?:To)?)\s*\(?\s*=\s*\(?['\"]([^'\"]+)['\"]",
    re.IGNORECASE,
)
_ONCLICK_URL_ARG_RE = re.compile(r"['\"]((?:https?://|/)[^'\"]+)['\"]")
# Common true-CAPTCHA gates we refuse to scrape even though the HTTP status is 200.
_SHELL_HINTS = (
    "captcha",
    "are you a robot",
    "verify you are human",
    "access denied",
    "cf-browser-verification",
    "enable javascript and cookies to continue",
)


def _random_proxy() -> Optional[str]:
    return choice(_PROXY_URLS) if _PROXY_URLS else None


class ScraperFallbackError(Exception):
    """Raised when every fetch tier fails or the page is an empty shell."""


@dataclass
class ScrapeResult:
    html: str
    final_url: str
    status_code: int = 200
    source: str = "playwright"
    content_metadata: Optional[dict] = field(default=None)


def _random_user_agent() -> str:
    return choice(USER_AGENTS)


def _looks_like_challenge(html: str) -> bool:
    lowered = html.lower()
    return any(hint in lowered for hint in _CLOUDFLARE_HINTS)


def _looks_like_shell(html: str) -> bool:
    lowered = html.lower()
    return any(hint in lowered for hint in _SHELL_HINTS)


def _score_html(html: str) -> int:
    """Return a rough measure of meaningful text length (no scripts/styles)."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "template"]):
        tag.decompose()
    blocks = soup.find_all(
        ["h1", "h2", "h3", "h4", "h5", "p", "li", "pre", "blockquote", "td"]
    )
    return sum(len(tag.get_text(" ", strip=True)) for tag in blocks)


def _discover_links(html: str, base_url: str) -> list[str]:
    """Discover navigation destinations from the rendered DOM.

    Covers plain ``<a href>`` links AND "click here" style JS buttons that carry
    their destination in data-* attributes or an ``onclick`` navigation string.
    Never clicks anything (no side effects); returns absolute, fragment-free URLs.
    """
    soup = BeautifulSoup(html, "html.parser")
    raw: set[str] = set()

    for a in soup.find_all("a"):
        href = a.get("href")
        if href:
            raw.add(str(href).strip())

    for el in soup.find_all(["button", "a", "div", "span", "li", "img"]):
        for attr in _JS_LINK_ATTRS:
            value = el.get(attr)
            if value:
                raw.add(str(value).strip())
        onclick = el.get("onclick")
        if not onclick:
            continue
        match = _ONCLICK_URL_RE.search(onclick)
        if match:
            raw.add(match.group(1))
        else:
            for arg in _ONCLICK_URL_ARG_RE.findall(onclick):
                raw.add(arg)

    resolved: set[str] = set()
    for href in raw:
        if not href or href.startswith("#"):
            continue
        if href.lower().startswith(("mailto:", "tel:", "javascript:", "data:")):
            continue
        try:
            full = urljoin(base_url, href)
        except ValueError:
            continue
        parts = urlsplit(full)
        if parts.scheme not in ("http", "https"):
            continue
        resolved.add(urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, "")))
    return sorted(resolved)


async def _scroll_through(page, max_steps: int = 15) -> None:
    """Trigger lazy-loading / infinite-scroll content by scrolling the page.

    Stops when the scroll height stops growing or `max_steps` is reached, so
    infinite scrollers do not hang the extraction.
    """
    prev_height = 0
    for _ in range(max_steps):
        try:
            height = await page.evaluate(
                "() => document.documentElement.scrollHeight"
            )
        except Exception:
            return
        if height <= prev_height:
            break
        try:
            await page.evaluate("window.scrollBy(0, window.innerHeight)")
        except Exception:
            return
        await page.wait_for_timeout(200)
        prev_height = height
    try:
        await page.evaluate("window.scrollTo(0, 0)")
    except Exception:
        pass
    await page.wait_for_timeout(250)


async def _scrape_playwright(
    url: str, timeout_seconds: int, attempt: int = 0
) -> ScrapeResult:
    """Render `url` with a stealth headless Chromium and return the DOM.

    `attempt` rotates user-agent, viewport and proxy so retries present a
    different fingerprint. Includes a lazy-load scroll pass before snapshot.
    """
    user_agent = USER_AGENTS[attempt % len(USER_AGENTS)]
    viewport = _VIEWPORTS[attempt % len(_VIEWPORTS)]
    proxy = _random_proxy()

    launch_kwargs: dict = {"headless": True, "args": _CHROMIUM_FLAGS}
    if proxy:
        launch_kwargs["proxy"] = {"server": proxy}

    async with async_playwright() as p:
        browser = await p.chromium.launch(**launch_kwargs)
        try:
            context = await browser.new_context(
                user_agent=user_agent,
                locale="en-US",
                viewport=viewport,
            )
            stealth = Stealth(navigator_user_agent_override=user_agent)
            await stealth.apply_stealth_async(context)

            page = await context.new_page()
            response = await page.goto(
                url,
                wait_until="networkidle",
                timeout=timeout_seconds * 1000,
            )
            status_code = response.status if response else 0

            html = await page.content()
            if _looks_like_challenge(html) or _looks_like_shell(html):
                # Challenges sometimes auto-pass after a few seconds.
                await page.wait_for_timeout(4000)
                html = await page.content()
                if _looks_like_challenge(html) or _looks_like_shell(html):
                    raise ScraperFallbackError("Cloudflare/CAPTCHA challenge detected")

            await _scroll_through(page)
            html = await page.content()
            final_url = page.url

            return ScrapeResult(
                html=html,
                final_url=final_url,
                status_code=status_code,
                source="playwright",
                content_metadata={"scroll_before_snapshot": True, "attempt": attempt},
            )
        finally:
            await browser.close()


async def _scrape_static(url: str, timeout_seconds: int) -> ScrapeResult:
    """Fetch `url` with httpx + trafilatura as a fast static fallback tier."""
    user_agent = _random_user_agent()
    timeout = httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 10))
    client_kwargs: dict = {
        "follow_redirects": True,
        "timeout": timeout,
        "headers": {
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    }
    proxy = _random_proxy()
    if proxy:
        client_kwargs["proxy"] = proxy
    async with httpx.AsyncClient(**client_kwargs) as client:
        response = await client.get(url)
        response.raise_for_status()

        html = response.text
        if _looks_like_challenge(html):
            raise ScraperFallbackError("Cloudflare challenge detected in static response")

        meta = {}
        try:
            metadata = trafilatura.extract_metadata(html, default_url=url)
            if metadata:
                meta = {
                    "title": metadata.title,
                    "author": metadata.author,
                    "date": metadata.date,
                }
        except Exception as exc:  # metadata extraction is best-effort
            logger.warning("trafilatura metadata failed: %s", exc)

        return ScrapeResult(
            html=html,
            final_url=str(response.url),
            status_code=response.status_code,
            source="static",
            content_metadata=meta,
        )


async def scrape_page(
    url: str,
    render_js: bool = True,
    timeout_seconds: int = 30,
) -> ScrapeResult:
    """Extract HTML from `url` with anti-bot retries and tier comparison.

    1. Dynamic tier (Playwright): up to `_MAX_DYNAMIC_ATTEMPTS` tries, rotating
       user-agent/viewport/proxy on challenge, timeout, or browser failure.
    2. Static tier (httpx + trafilatura) always runs in parallel when `render_js`
       is enabled; it is cheap and can win on pages that render server-side.
    3. Whichever tier produced the most meaningful text wins (content-quality
       comparison); empty-shell pages (CAPTCHA gates, JS shells) are rejected.
    4. Navigation destinations (incl. JS button links) are discovered and
       attached to `content_metadata["discovered_links"]`.
    """
    dynamic_result: Optional[ScrapeResult] = None
    if render_js:
        for attempt in range(_MAX_DYNAMIC_ATTEMPTS):
            try:
                dynamic_result = await asyncio.wait_for(
                    _scrape_playwright(url, timeout_seconds, attempt),
                    timeout=timeout_seconds,
                )
                break
            except (
                asyncio.TimeoutError,
                PlaywrightTimeoutError,
                PlaywrightError,
                MemoryError,
                ScraperFallbackError,
            ) as exc:
                logger.warning(
                    "dynamic attempt %d failed for %s (%s)",
                    attempt + 1,
                    url,
                    exc,
                )

    static_result: Optional[ScrapeResult] = None
    try:
        static_result = await _scrape_static(url, timeout_seconds)
    except Exception as exc:
        logger.warning("static tier failed for %s (%s)", url, exc)

    candidates = [r for r in (dynamic_result, static_result) if r is not None]
    if not candidates:
        raise ScraperFallbackError(
            "All fetch tiers failed; nothing scrapable was returned"
        )

    best = max(candidates, key=lambda r: _score_html(r.html))
    score = _score_html(best.html)
    if score < _SHELL_MIN_SCORE:
        raise ScraperFallbackError(
            f"Page appeared empty (content score {score} below shell threshold)"
        )

    links = _discover_links(best.html, best.final_url)
    meta = dict(best.content_metadata or {})
    meta["content_score"] = score
    meta["discovered_links"] = links
    meta["tier_scores"] = {c.source: _score_html(c.html) for c in candidates}
    best.content_metadata = meta
    return best
