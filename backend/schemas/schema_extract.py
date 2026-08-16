from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SchemaExtractRequest(BaseModel):
    """Request payload for POST /api/v1/schema."""

    markdown: str = Field(description="Clean markdown to structure.")
    json_schema: dict[str, Any] = Field(
        description="JSON Schema definition the LLM output must conform to."
    )
    max_tokens: int = Field(
        default=1024, ge=128, le=8192, description="LLM response token budget."
    )


class SchemaExtractResponse(BaseModel):
    """Response payload returned by POST /api/v1/schema."""

    success: bool = Field(description="True when structured output was produced.")
    data: dict[str, Any] = Field(description="Validated structured JSON output.")
    provider: Literal["groq", "openai", "ollama"] = Field(
        description="Provider that produced the output."
    )
    model: str = Field(description="Model identifier used.")
    usage: dict[str, Any] = Field(description="Prompt/completion token usage.")