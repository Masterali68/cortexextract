from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class ExtractionRequest(BaseModel):
    """Request payload for POST /api/v1/extract."""

    url: HttpUrl = Field(description="Target page URL to extract.")
    render_js: bool = Field(
        default=True, description="Render with Playwright when True; static fetch otherwise."
    )
    strip_noise: bool = Field(
        default=True,
        description="Run the DOM cleaner to remove navbars, footers, scripts, and ads.",
    )
    timeout_seconds: int = Field(
        default=30,
        ge=5,
        le=60,
        description="Hard cap on total extraction time in seconds.",
    )


class ExtractionResponse(BaseModel):
    """Response payload returned by POST /api/v1/extract."""

    success: bool = Field(description="True when extraction produced usable content.")
    status_code: int = Field(description="HTTP status code observed from the target.")
    execution_time_ms: float = Field(description="Total extraction wall time in ms.")
    title: str = Field(description="Document title extracted from the page.")
    raw_html: str = Field(description="Raw HTML fetched from the target page.")
    clean_markdown: str = Field(
        description="GFM markdown with noise stripped and content preserved."
    )
    metadata: dict[str, Any] = Field(
        description="Extraction metadata: source tier, final URL, renderer, token count."
    )