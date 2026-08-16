from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from fastapi import Request

BYOK_HEADERS = {
    "x-groq-key",
    "x-openai-key",
    "x-ollama-endpoint",
    "x-llm-provider",
}

_DEFAULT_OLLAMA_ENDPOINT = "http://localhost:11434"

_PROVIDER_HEADERS = {
    "groq": "x-groq-key",
    "openai": "x-openai-key",
    "ollama": "x-ollama-endpoint",
}

_MASKED = "***"


def mask(value: str) -> str:
    """Mask a secret for any log/display surface while preserving shape."""
    if not value:
        return ""
    if len(value) <= 8:
        return _MASKED
    return f"{value[:3]}...{value[-3:]}"


def _is_private_or_loopback(host: str) -> bool:
    host = host.strip().lower()
    if host in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
    )


@dataclass(frozen=True)
class ByokCredentials:
    """Volatile BYOK credentials scoped to a single request.

    Never persisted: no logs, no disk, no database, no repr leak.
    """

    provider: str = ""
    groq_key: str = ""
    openai_key: str = ""
    ollama_endpoint: str = ""

    @property
    def active_key(self) -> str:
        if self.provider == "groq":
            return self.groq_key
        if self.provider == "openai":
            return self.openai_key
        return ""

    def __repr__(self) -> str:
        return (
            "ByokCredentials("
            f"provider={self.provider!r}, "
            f"groq_key={mask(self.groq_key)!r}, "
            f"openai_key={mask(self.openai_key)!r}, "
            f"ollama_endpoint={self.ollama_endpoint!r})"
        )


def extract_credentials(request: Request) -> ByokCredentials:
    """Read BYOK headers off `request` into a volatile, redacted credential set."""
    provider = (request.headers.get("x-llm-provider") or "").strip().lower()

    groq_key = request.headers.get("x-groq-key") or ""
    openai_key = request.headers.get("x-openai-key") or ""

    raw_endpoint = (request.headers.get("x-ollama-endpoint") or "").strip()
    if raw_endpoint:
        host = urlsplit(raw_endpoint).hostname or ""
        if not _is_private_or_loopback(host):
            raw_endpoint = _DEFAULT_OLLAMA_ENDPOINT
    else:
        raw_endpoint = _DEFAULT_OLLAMA_ENDPOINT

    return ByokCredentials(
        provider=provider,
        groq_key=groq_key,
        openai_key=openai_key,
        ollama_endpoint=raw_endpoint,
    )


def strip_from_scope(request: Request) -> None:
    """Zero-logging guard: remove BYOK header values from the ASGI scope.

    Call AFTER extracting credentials so values survive only in
    `request.state.byok` for the request lifetime.
    """
    headers = request.scope.get("headers", [])
    request.scope["headers"] = [
        (name, value)
        for name, value in headers
        if name.decode("latin-1").lower() not in BYOK_HEADERS
    ]