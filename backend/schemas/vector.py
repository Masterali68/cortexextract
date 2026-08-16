from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class VectorIngestRequest(BaseModel):
    """Request payload for POST /api/v1/vector (ingest)."""

    markdown: str = Field(description="Markdown content to chunk, embed, and store.")
    title: str = Field(default="", description="Optional document title.")
    source_url: str = Field(default="", description="Origin URL of the document.")
    chunk_mode: Literal["fixed", "semantic", "heading"] = Field(
        default="fixed", description="Chunking mode applied before embedding."
    )
    max_tokens: int = Field(
        default=512, ge=32, le=2048, description="Chunk token budget."
    )


class VectorIngestResponse(BaseModel):
    """Response payload returned by POST /api/v1/vector."""

    success: bool = Field(description="True when documents were stored.")
    inserted: int = Field(description="Number of chunks embedded and inserted.")
    total_documents: int = Field(description="Documents now in the store.")
    provider: Literal["ollama", "openai"] = Field(
        description="Embedding provider used."
    )


class VectorSearchRequest(BaseModel):
    """Request payload for POST /api/v1/vector/search."""

    query: str = Field(description="Natural-language query to search for.")
    top_k: int = Field(default=5, ge=1, le=50, description="Number of results.")


class VectorHit(BaseModel):
    """A single vector search result."""

    content: str = Field(description="Matching chunk text.")
    source_url: str = Field(description="Origin URL of the document.")
    title: str = Field(description="Document title.")
    score: float = Field(description="Cosine similarity score (0–1).")
    token_count: int = Field(description="Tokens in the chunk.")


class VectorSearchResponse(BaseModel):
    """Response payload returned by POST /api/v1/vector/search."""

    success: bool = Field(description="True when the search completed.")
    provider: Literal["ollama", "openai"] = Field(description="Embedding provider used.")
    results: list[VectorHit] = Field(description="Ranked search hits.")