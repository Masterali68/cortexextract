from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    """Request payload for POST /api/v1/ask (RAG question answering)."""

    question: str = Field(
        min_length=1,
        max_length=2000,
        description="Natural-language question to answer from the vector store.",
    )
    top_k: int = Field(
        default=8, ge=1, le=10, description="Number of context chunks to retrieve."
    )
    max_tokens: int = Field(
        default=1024, ge=128, le=2048, description="Answer token budget."
    )


class AskSource(BaseModel):
    """A retrieved context chunk used to answer an Ask query."""

    content: str = Field(description="Chunk text.")
    title: str = Field(description="Document title.")
    source_url: str = Field(description="Origin URL of the document.")
    score: float = Field(description="Cosine similarity score (0–1).")
    token_count: int = Field(description="Tokens in the chunk.")


class AskResponse(BaseModel):
    """Response payload returned by POST /api/v1/ask."""

    success: bool = Field(description="True when an answer was produced.")
    question: str = Field(description="The question asked.")
    answer: str = Field(description="LLM answer grounded in retrieved context.")
    sources: list[AskSource] = Field(description="Retrieved chunks that grounded the answer.")
    provider: Literal["groq", "openai", "ollama"] = Field(
        description="Provider that produced the answer."
    )
    model: str = Field(description="Model identifier used.")
    usage: dict[str, Any] = Field(description="Prompt/completion token usage.")