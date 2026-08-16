# Contributing to CortexExtract

Thanks for helping make web extraction deterministic for everyone. This project is open source by design — the goal is a tool others can actually run, extend, and trust.

## Ground rules

1. **Zero-trust BYOK security is non-negotiable.** User API keys must stay client-side, travel only via per-request headers (`X-Groq-Key`, `X-OpenAI-Key`), and must never be logged, persisted, or leaked. A PR that violates this will be rejected.
2. **No `any` in TypeScript.** Every component and store is explicitly typed.
3. **Every extraction path must preserve content.** Noise pruning should never destroy contact info, links, or data. When you strip something, ask "could anyone need this?"
4. **Never guess URLs or credentials** in docs or code.

## Development workflow

- Fork, create a branch, and open a PR against `main`.
- Backend changes ship with tests. The suite must stay green:
  ```bash
  cd backend && source venv/bin/activate && python -m pytest tests -q
  ```
- Frontend changes must pass all three gates:
  ```bash
  cd frontend && npx tsc --noEmit && npm run lint && npm run build
  ```
- Keep API latency targets: < 1.5s for static sites, < 4.0s for heavy dynamic SPA renders.

## Test conventions

- Backend tests use plain `pytest` (no `pytest-asyncio`); async tests wrap coroutines in `asyncio.run()`.
- Monkeypatching: stub module attributes and restore them, or design around them (e.g. use `use_index=False` in crawler tests instead of stubbing index discovery).
- New features get a focused test file — the suite currently covers the cleaner (incl. contact preservation), crawler, chunkers, ask/retrieval, schemas, and pipeline.

## Areas that need help

- Embedding provider abstraction beyond Ollama/OpenAI
- Batch URL ingestion
- LLM-powered schema suggestions
- More browser fixtures for anti-bot evasion tests

## Reporting issues

Include: the target URL, expected vs. actual output, the API response (with keys redacted), and whether it reproduces with `render_js=true` or `false`.