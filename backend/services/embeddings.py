from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger("cortexextract.embeddings")

_OLLAMA_ENDPOINT = os.getenv("OLLAMA_ENDPOINT", "http://localhost:11434")
_OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")


class EmbeddingsError(Exception):
    """Raised when an embedding provider fails."""


async def embed_texts(
    texts: list[str],
    provider: str = "ollama",
    api_key: str = "",
    endpoint: str = "",
) -> list[list[float]]:
    """Embed a list of texts into vectors.

    `provider` is one of "ollama" | "openai". For Ollama the endpoint may be
    overridden per-request (guarded to loopback in the BYOK layer). OpenAI uses
    the `api_key` supplied as a BYOK header.
    """
    if not texts:
        return []

    if provider == "ollama":
        return await _embed_ollama(texts, endpoint or _OLLAMA_ENDPOINT)
    if provider == "openai":
        return await _embed_openai(texts, api_key)
    raise EmbeddingsError("X-LLM-Provider must be ollama or openai for embeddings")


async def _embed_ollama(texts: list[str], endpoint: str) -> list[list[float]]:
    vectors: list[list[float]] = []
    base = endpoint.rstrip("/")
    async with httpx.AsyncClient(timeout=120) as client:
        for text in texts:
            response = await client.post(
                f"{base}/api/embeddings",
                json={"model": _OLLAMA_EMBED_MODEL, "prompt": text},
            )
            if response.status_code != 200:
                raise EmbeddingsError(
                    f"Ollama embeddings {response.status_code}: {response.text[:200]}"
                )
            vectors.append(response.json()["embedding"])
    return vectors


async def _embed_openai(texts: list[str], api_key: str) -> list[list[float]]:
    if not api_key:
        raise EmbeddingsError("Missing X-OpenAI-Key header for embeddings")
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": "text-embedding-3-small", "input": texts},
        )
        if response.status_code != 200:
            raise EmbeddingsError(
                f"OpenAI embeddings {response.status_code}: {response.text[:200]}"
            )
        body = response.json()
        vectors = [item["embedding"] for item in body.get("data", [])]
    return vectors


def encode_vector(vector: list[float]) -> str:
    """Encode a float vector for a pgvector SQL parameter (cube-compatible)."""
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"


def decode_vector(raw: Any) -> list[float]:
    """Decode a pgvector string back into a float list."""
    if isinstance(raw, (list, tuple)):
        return [float(value) for value in raw]
    return [float(value) for value in str(raw).strip("[]").split(",") if value != ""]