from __future__ import annotations

import asyncio
import logging
import re
from urllib.parse import urlsplit, urlunsplit

import httpx

from services.chunker import chunk, heading_path, strip_boilerplate
from services.cleaner import DomCleaner, extract_title
from services.embeddings import embed_texts
from services.scraper import ScraperFallbackError, scrape_page
from services import vector_store

logger = logging.getLogger("cortexextract.crawler")

_POLITENESS_DELAY_SECONDS = 0.3

# Link targets that are never crawled as pages (media, archives, static assets).
_IGNORED_EXTENSIONS = {
    "pdf", "png", "jpg", "jpeg", "gif", "webp", "svg", "ico", "bmp", "tiff",
    "zip", "tar", "gz", "7z", "rar", "mp3", "mp4", "mov", "avi", "webm", "m4a",
    "css", "js", "woff", "woff2", "ttf", "eot",
}


def normalize_url(url: str) -> str:
    """Lowercase scheme/host, drop fragment, drop default ports, keep path+query."""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return ""
    host = (parts.hostname or "").lower()
    if not host:
        return ""
    scheme = parts.scheme.lower() or "https"
    port = ""
    try:
        if parts.port and not (
            (scheme == "http" and parts.port == 80)
            or (scheme == "https" and parts.port == 443)
        ):
            port = f":{parts.port}"
    except ValueError:
        pass
    return urlunsplit((scheme, f"{host}{port}", parts.path or "/", parts.query, ""))


def same_host(a: str, b: str) -> bool:
    """True when two URLs share the same netloc (host[:port])."""
    netloc_a = urlsplit(normalize_url(a)).netloc
    netloc_b = urlsplit(normalize_url(b)).netloc
    return bool(netloc_a and netloc_a == netloc_b)


def is_ignorable(url: str) -> bool:
    """True for asset/media/archive links we should not treat as pages."""
    path = urlsplit(url).path.lower()
    filename = path.rsplit("/", 1)[-1]
    if "." not in filename:
        return False
    extension = filename.rsplit(".", 1)[-1]
    return extension in _IGNORED_EXTENSIONS


def _parse_llms_txt(text: str) -> list[str]:
    """Extract absolute markdown links from an llms.txt index file."""
    return re.findall(r"\[[^\]]*\]\((https?://[^\s)]+)\)", text)


def _parse_sitemap(text: str) -> list[str]:
    """Extract <loc> URL entries from a sitemap.xml document."""
    locs = re.findall(r"<loc>\s*([^<]*?)\s*</loc>", text, re.IGNORECASE | re.DOTALL)
    return [loc.strip() for loc in locs if loc.strip().startswith(("http://", "https://"))]


def _index_candidates(seed_url: str) -> list[str]:
    """Probe URLs for llms.txt / sitemap.xml, walking the seed path upward.

    Docs sites commonly host these at the origin root, at a /docs/ base, or
    deep under the seed's directory; probe each level concurrently.
    """
    parts = urlsplit(seed_url)
    origin = f"{parts.scheme or 'https'}://{parts.netloc}"
    segments = [segment for segment in (parts.path or "").split("/") if segment]
    dirs = ["/".join(segments[:i]) for i in range(len(segments), 0, -1)] + [""]
    candidates: list[str] = []
    for directory in dirs:
        base = f"{origin}/{directory}" if directory else origin
        candidates.extend((f"{base}/llms.txt", f"{base}/sitemap.xml"))
    return candidates


async def _fetch_text(session: httpx.AsyncClient, url: str, timeout: float) -> str | None:
    try:
        response = await session.get(url, timeout=timeout)
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    text = response.text or ""
    return text if text.strip() else None


def _is_markdown_url(url: str) -> bool:
    """True when the URL points at a raw markdown source (.md / .markdown)."""
    path = urlsplit(url).path.lower()
    return path.endswith(".md") or path.endswith(".markdown")


def _markdown_title(markdown: str) -> str:
    """First markdown heading as a page title, falling back to the first line."""
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return re.sub(r"^#+\s*", "", stripped).strip()[:160]
    first = next((line.strip() for line in markdown.splitlines() if line.strip()), "")
    return first[:160]


async def _fetch_markdown(
    session: httpx.AsyncClient,
    url: str,
    timeout: float,
) -> str | None:
    """Fetch a raw markdown source, returning None unless served as text/markdown."""
    try:
        response = await session.get(url, timeout=timeout)
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    content_type = (response.headers.get("content-type", "") or "").lower()
    if not content_type.startswith(("text/markdown", "text/x-markdown")):
        return None
    text = response.text or ""
    return text if text.strip() else None


async def discover_index_urls(
    seed_url: str,
    session: httpx.AsyncClient,
    timeout: float = 8.0,
) -> tuple[str | None, str | None, list[str]]:
    """Find a site-wide page index (llms.txt preferred, then sitemap.xml).

    Returns (index_url, kind, urls). kind is ``"llms"``, ``"sitemap"``, or
    ``None`` when no index is available. URLs are absolute and de-duplicated.
    """
    if not urlsplit(seed_url).netloc:
        return None, None, []
    candidates = _index_candidates(seed_url)
    results = await asyncio.gather(
        *[_fetch_text(session, candidate, timeout) for candidate in candidates],
        return_exceptions=True,
    )
    fetched = {
        candidate: text
        for candidate, text in zip(candidates, results)
        if isinstance(text, str) and text.strip()
    }

    llms_index = next((c for c in candidates if "llms.txt" in c and c in fetched), None)
    sitemap_index = next((c for c in candidates if "sitemap.xml" in c and c in fetched), None)

    urls: list[str] = []
    index_url: str | None = None
    index_kind: str | None = None
    if llms_index:
        urls.extend(_parse_llms_txt(fetched[llms_index]))
        index_url, index_kind = llms_index, "llms"
    if sitemap_index:
        urls.extend(_parse_sitemap(fetched[sitemap_index]))
        if index_url is None:
            index_url, index_kind = sitemap_index, "sitemap"

    seen: set[str] = set()
    cleaned: list[str] = []
    for url in urls:
        normalized = normalize_url(url)
        if normalized and normalized not in seen:
            seen.add(normalized)
            cleaned.append(url)
    return index_url, index_kind, cleaned


async def crawl_site(
    url: str,
    max_pages: int = 25,
    max_depth: int = 3,
    render_js: bool = True,
    timeout_seconds: int = 30,
    strip_noise: bool = True,
    chunk_mode: str = "heading",
    chunk_max_tokens: int = 512,
    store_vectors: bool = True,
    embed_provider: str = "ollama",
    api_key: str = "",
    ollama_endpoint: str = "",
    use_index: bool = True,
) -> dict:
    """Breadth-first crawl of the same-origin site reachable from `url`.

    Each page is scraped (with the smart scraper: retries, tier comparison,
    lazy-load scroll), cleaned to GFM, chunked, embedded and upserted into the
    vector store idempotently. Per-page failures are collected, never fatal.

    When ``use_index`` is enabled the crawl first probes for an llms.txt /
    sitemap.xml index and seeds the queue with the full site list instead of
    relying purely on link-following, which misses pages nothing links to.
    """
    seed = normalize_url(url)
    if not seed:
        raise ScraperFallbackError("Invalid seed URL")
    if not same_host(url, seed):
        seed = url

    seed_key = normalize_url(url)
    index_url = None
    index_kind = None
    index_set: set[str] = set()
    index_order: list[str] = []
    if use_index:
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(10.0)) as session:
                index_url, index_kind, index_urls = await discover_index_urls(url, session)
        except Exception:
            logger.warning("index discovery failed for %s; falling back to BFS", url, exc_info=True)
            index_url, index_kind, index_urls = None, None, []
        if index_url and index_urls:
            for candidate in index_urls:
                normalized = normalize_url(candidate)
                if (
                    normalized
                    and normalized not in index_set
                    and same_host(candidate, seed)
                    and not is_ignorable(candidate)
                ):
                    index_set.add(normalized)
                    index_order.append(normalized)

    if index_set:
        strategy = f"index:{index_kind}" if index_kind else "index"
        queue: list[tuple[str, int]] = [(url, 0)]
        for candidate_key in index_order:
            if len(queue) >= max_pages:
                break
            if candidate_key != seed_key:
                queue.append((candidate_key, 0))
    else:
        strategy = "bfs"
        queue = [(url, 0)]

    cleaner = DomCleaner()
    visited: set[str] = set()
    failures: list[dict] = []
    pages: list[dict] = []
    chunks_stored_total = 0

    client_timeout = httpx.Timeout(max(timeout_seconds, 10.0))
    async with httpx.AsyncClient(follow_redirects=True, timeout=client_timeout) as session:
        while queue and len(pages) < max_pages:
            current, depth = queue.pop(0)
            key = normalize_url(current)
            if key in visited:
                continue
            visited.add(key)
            via = "index" if key in index_set else ("seed" if key == seed_key else "link")

            try:
                markdown: str | None = None
                scrape_meta: dict = {}
                if _is_markdown_url(current):
                    raw = await _fetch_markdown(session, current, timeout_seconds)
                    if raw and raw.strip():
                        markdown = raw
                        title = _markdown_title(raw)
                        scrape_meta = {
                            "content_score": len(raw),
                            "discovered_links": _parse_llms_txt(raw),
                        }
                if markdown is None:
                    scrape = await scrape_page(
                        current,
                        render_js=render_js,
                        timeout_seconds=timeout_seconds,
                    )
                    markdown = cleaner.clean(scrape.html, strip_noise=strip_noise)
                    if not markdown.strip():
                        raise ScraperFallbackError("No usable markdown content")
                    title = extract_title(scrape.html)
                    scrape_meta = scrape.content_metadata or {}

                inserted = 0
                if store_vectors:
                    await vector_store.ensure_schema()
                    vector_markdown = strip_boilerplate(markdown)
                    chunks_list = chunk(
                        vector_markdown,
                        mode=chunk_mode,
                        max_tokens=chunk_max_tokens,
                        overlap=0.1,
                    )
                    vectors = await embed_texts(
                        [c.content for c in chunks_list],
                        provider=embed_provider,
                        api_key=api_key,
                        endpoint=ollama_endpoint,
                    )
                    documents = [
                        vector_store.Document(
                            source_url=current,
                            title=title,
                            content=c.content,
                            token_count=c.token_count,
                            embedding=vector,
                            metadata={
                                "chunk_index": idx,
                                "section": heading_path(c.content),
                                "crawl": True,
                                "markdown_source": _is_markdown_url(current),
                            },
                        )
                        for idx, (c, vector) in enumerate(zip(chunks_list, vectors))
                    ]
                    inserted = await vector_store.upsert_documents(documents)
                    chunks_stored_total += inserted

                discovered = scrape_meta.get("discovered_links", [])
                pages.append(
                    {
                        "url": current,
                        "title": title,
                        "chunks_stored": inserted,
                        "content_score": scrape_meta.get("content_score", 0),
                        "discovered_links": len(discovered),
                        "via": via,
                    }
                )

                if depth < max_depth:
                    for link in discovered:
                        normalized = normalize_url(link)
                        if (
                            normalized
                            and normalized not in visited
                            and same_host(link, seed)
                            and not is_ignorable(link)
                        ):
                            queue.append((link, depth + 1))

                await asyncio.sleep(_POLITENESS_DELAY_SECONDS)
            except Exception as exc:  # per-page failure is not fatal
                logger.warning("crawl page failed for %s: %s", current, exc)
                failures.append({"url": current, "error": str(exc)})

    total = await vector_store.count_documents() if store_vectors else 0
    return {
        "seed_url": seed,
        "strategy": strategy,
        "index_used": index_url,
        "pages_crawled": len(pages),
        "chunks_stored": chunks_stored_total,
        "total_documents": total,
        "failures": failures,
        "pages": pages,
    }