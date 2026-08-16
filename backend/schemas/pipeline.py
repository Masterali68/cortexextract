from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from .chunk import ChunkItem


class PipelineRequest(BaseModel):
    """Request payload for POST /api/v1/pipeline (extract + process + store)."""

    url: str = Field(description="URL to extract.")
    render_js: bool = Field(default=True, description="Render with Playwright first.")
    strip_noise: bool = Field(default=True, description="Prune structural noise.")
    timeout_seconds: int = Field(
        default=30, ge=5, le=60, description="Per-tier fetch timeout."
    )
    chunk_mode: Literal["fixed", "semantic", "heading"] = Field(
        default="heading", description="Chunking mode for the vector store + chunks tab."
    )
    chunk_max_tokens: int = Field(
        default=512, ge=32, le=2048, description="Chunk token budget."
    )
    generate_schema: bool = Field(
        default=True, description="Run LLM JSON-schema extraction via BYOK provider."
    )
    store_vectors: bool = Field(
        default=True, description="Chunk, embed, and upsert into pgvector."
    )
    schema_max_tokens: int = Field(
        default=1024, ge=128, le=8192, description="Schema LLM response budget."
    )


class PipelineStats(BaseModel):
    """Token metrics for the extracted markdown."""

    characters: int
    words: int
    tokens_cl100k: int
    tokens_o200k: int


class SchemaMeta(BaseModel):
    """Outcome of the optional schema-extraction step."""

    provider: str | None = Field(description="Provider used, if the step ran.")
    model: str | None = Field(description="Model used, if the step ran.")
    error: str | None = Field(description="Non-fatal error, if the step failed.")


class VectorResult(BaseModel):
    """Outcome of the optional vector-store step."""

    stored: bool = Field(description="True when chunks were embedded and upserted.")
    inserted: int = Field(description="Number of chunks inserted.")
    total_documents: int = Field(description="Documents now in the store.")
    error: str | None = Field(description="Non-fatal error, if the step failed.")


class PipelineResponse(BaseModel):
    """Response payload returned by POST /api/v1/pipeline."""

    success: bool = Field(description="True when extraction + processing completed.")
    execution_time_ms: float = Field(description="Total pipeline wall time (ms).")
    title: str = Field(description="Page title.")
    metadata: dict[str, Any] = Field(description="Extraction metadata.")
    clean_markdown: str = Field(description="Cleaned GFM markdown.")
    raw_html: str = Field(description="Raw HTML captured for source preview.")
    stats: PipelineStats = Field(description="Token metrics.")
    chunks: list[ChunkItem] = Field(description="Chunks produced by the chunker.")
    schema_output: dict[str, Any] | None = Field(
        default=None, description="Validated JSON schema output, if generated."
    )
    schema_meta: SchemaMeta | None = Field(
        default=None, description="Schema-step outcome details."
    )
    vector: VectorResult | None = Field(
        default=None, description="Vector-store step outcome."
    )