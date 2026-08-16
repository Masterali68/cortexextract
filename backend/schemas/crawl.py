from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

ChunkMode = Literal["fixed", "semantic", "heading"]


class CrawlRequest(BaseModel):
    """Request payload for POST /api/v1/crawl (same-origin site crawl)."""

    url: str = Field(description="Seed URL. Only same-host sub-links are crawled.")
    max_pages: int = Field(25, ge=1, le=100, description="Hard cap on pages to visit.")
    max_depth: int = Field(3, ge=1, le=10, description="Max link depth from the seed.")
    use_index: bool = Field(
        True,
        description="Probe for llms.txt / sitemap.xml first to seed the whole site list.",
    )
    render_js: bool = Field(True, description="Render each page with Playwright.")
    timeout_seconds: int = Field(30, ge=5, le=120)
    strip_noise: bool = Field(True)
    chunk_mode: ChunkMode = Field("heading")
    chunk_max_tokens: int = Field(512, ge=64, le=4096)
    store_vectors: bool = Field(True)

    @field_validator("url")
    @classmethod
    def _url_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("url is required")
        return stripped


class CrawlPageResult(BaseModel):
    """One crawled page and its outcome."""

    url: str
    title: str
    chunks_stored: int
    content_score: int
    discovered_links: int
    via: str = Field("link", description="How the page was reached: index | seed | link.")


class CrawlFailure(BaseModel):
    """A page that could not be scraped, with the reason."""

    url: str
    error: str


class CrawlResponse(BaseModel):
    """Summary returned by POST /api/v1/crawl."""

    success: bool
    seed_url: str
    strategy: str = Field("bfs", description="index:llms | index:sitemap | bfs")
    index_used: str | None = Field(None, description="Index URL that seeded the crawl, if any.")
    pages_crawled: int
    chunks_stored: int
    total_documents: int
    failures: list[CrawlFailure]
    pages: list[CrawlPageResult]
    elapsed_ms: float