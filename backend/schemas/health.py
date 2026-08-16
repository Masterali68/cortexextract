from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check payload returned by GET /health."""

    status: Literal["ok"] = Field(description="Service health status.")
    timestamp: datetime = Field(
        description="ISO-8601 UTC timestamp of the health check."
    )
    version: str = Field(description="Backend API version.")
    redis: bool = Field(default=False, description="Redis connectivity probe.")
    postgres: bool = Field(default=False, description="Postgres connectivity probe.")