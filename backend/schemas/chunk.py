from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ChunkRequest(BaseModel):
    """Request payload for POST /api/v1/chunk."""

    text: str = Field(description="Markdown or plain text to chunk.")
    mode: Literal["fixed", "semantic", "heading"] = Field(
        default="fixed", description="Chunking algorithm to apply."
    )
    max_tokens: int = Field(
        default=512, ge=32, le=2048, description="Target token budget per chunk."
    )
    overlap: float = Field(
        default=0.1, ge=0.0, le=0.5, description="Overlap ratio (fixed mode only)."
    )


class ChunkItem(BaseModel):
    """A single chunk with char offsets and exact token count."""

    content: str = Field(description="Chunk text.")
    start: int = Field(description="Character offset of chunk start.")
    end: int = Field(description="Character offset of chunk end.")
    token_count: int = Field(description="Exact token count (cl100k_base).")


class ChunkStats(BaseModel):
    """Aggregate token/text metrics for a chunking run."""

    characters: int = Field(description="Total characters in source text.")
    words: int = Field(description="Total word count in source text.")
    tokens_cl100k: int = Field(description="Source tokens under cl100k_base.")
    tokens_o200k: int = Field(description="Source tokens under o200k_base.")
    total_chunks: int = Field(description="Number of chunks produced.")


class ChunkResponse(BaseModel):
    """Response payload returned by POST /api/v1/chunk."""

    mode: Literal["fixed", "semantic", "heading"] = Field(description="Applied mode.")
    max_tokens: int = Field(description="Applied token budget.")
    chunks: list[ChunkItem] = Field(description="Produced chunks.")
    stats: ChunkStats = Field(description="Aggregate metrics for the run.")