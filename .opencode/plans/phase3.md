# Phase 3 — BYOK Security Architecture & RAG Token Processing

## Analysis & Reconciliation Notes
- Phase 2 ships: `schemas/extraction.py`, `services/scraper.py`, `services/cleaner.py`, `POST /api/v1/extract`, and a `sanitize_byok_headers` middleware in `main.py` that **strips** BYOK headers from scope (zero-logging, but makes them unreadable downstream).
- `services/metrics.py` (Phase 1) counts tokens with `cl100k_base` only. `services/chunker/` is an empty stub package from Phase 1.
- **Decisions:** (1) `services/token_counter.py` supersedes `metrics.py`; update `main.py` imports and delete `metrics.py`. (2) Replace the empty `chunker/` package with a `services/chunker.py` module. (3) Rework the middleware: extract BYOK keys into `request.state` **before** zero-logging strip, so `/api/v1/schema` can read them via `request.state`.

## 1. Volatile BYOK Header Interceptor — `backend/services/byok.py`
```python
@dataclass
class ByokCredentials:
    provider: str            # "groq" | "openai" | "ollama" | ""
    groq_key: str = ""
    openai_key: str = ""
    ollama_endpoint: str = ""   # default "http://localhost:11434"
```
- `extract_credentials(request) -> ByokCredentials` reads `X-Groq-Key`, `X-OpenAI-Key`, `X-Ollama-Endpoint`, `X-LLM-Provider`.
- `ByokCredentials` is **volatile**: kept only in `request.state.byok` for the request lifetime; never pickled, cached, or written.
- **Zero-logging safeguards (AGENTS.md rule 1):** keys never appear in logs, console, tracebacks, or DB. The existing middleware is upgraded to (a) copy key values into `request.state`, (b) then strip them from `request.scope["headers"]` before handlers run, (c) a `repr` override redacts all credential fields (`***`).
- **SSRF guard for Ollama:** `X-Ollama-Endpoint` is coerced to `http://localhost:11434` unless it matches a loopback/private range — blocks using the gateway as an open LLM proxy.

## 2. Token Metrics Service — `backend/services/token_counter.py`
- `count_tokens(text, encoding="cl100k_base" | "o200k_base") -> int` via `tiktoken`.
- `TokenStats` dataclass: `characters`, `words` (`len(text.split())`), `tokens_cl100k`, `tokens_o200k`, `encoding` per field.
- `compute_stats(text) -> TokenStats`; supersedes `metrics.py` (deleted, imports updated in `main.py`).

## 3. RAG Semantic Chunking Engine — `backend/services/chunker.py`
- `chunk(text, mode, max_tokens=512, overlap=0.1) -> list[Chunk]`; `Chunk` has `content`, `start`, `end`, `token_count`.
- **Mode `fixed`:** sliding token window via `tiktoken`; `overlap` = `int(max_tokens * 0.1)` token overlap (AGENTS.md: 10%).
- **Mode `semantic`:** split on sentence/paragraph boundaries (`\n\n` then `. `) keeping context boundaries; merge chunks until `max_tokens`.
- **Mode `heading`:** split on `#`, `##`, `###` headings, preserving heading in the chunk; oversize sections re-split by `fixed`.
- Boundary-aware: never split mid-sentence unless a single unit exceeds `max_tokens`.

## 4. Schema Extraction Route — `POST /api/v1/schema`
- New `schemas/schema_extract.py`: `SchemaExtractRequest { markdown: str, json_schema: dict, max_tokens: int = 1024 }` and `SchemaExtractResponse { success: bool, data: dict, provider: str, model: str, usage: dict }`.
- Flow in `main.py`: read `request.state.byok` → pick provider via `X-LLM-Provider` → POST clean markdown + `json_schema` to the provider's OpenAI-compatible chat completions endpoint (Groq/OpenAI via httpx; Ollama at the guarded endpoint).
- Output parsed with Pydantic (`data` field validated against `json_schema` semantics); non-200 → `502`.
- `metadata.token_count` in `/api/v1/extract` now uses `compute_stats` (both encodings).

## 5. Verification
- `/api/v1/extract` returns `characters`/`words`/`tokens_cl100k`/`tokens_o200k` in `metadata`.
- Chunker unit check on a 5KB fixture: 3 modes produce expected chunk counts and 10% overlap in `fixed`.
- BYOK interceptor: send `X-Groq-Key: sk-secret` → `request.state.byok.groq_key` populated, **not** in backend logs; `repr(byok)` shows `***`.
- `/api/v1/schema` against local Ollama (if running) or dry-run mock asserting the payload sent to the provider is exactly markdown + schema (no keys in body).

## Dependencies Added
None — `httpx` + `tiktoken` already present. Provider calls use OpenAI-compatible REST (no SDK).

## Out of Scope (Phase 4+)
pgvector embedding ingestion, persistence layer, multi-document RAG.