# Phase 2 — Multi-Tiered Scraper Architecture

## Analysis & Reconciliation Notes
- AGENTS.md mandates: Playwright-first with **automatic static fallback** (httpx + trafilatura), DOM noise stripping (script/style/nav/footer/header/iframe/cookie modals), GFM markdown purity with preserved code blocks/tables/alt-text, exact token metrics, strict Pydantic v2 schemas, latency caps (<1.5s static, <4.0s heavy SPA), and zero-logging of BYOK headers.
- Phase 1 already shipped `schemas/extract.py` (`ExtractRequest`/`ExtractResponse`) and `POST /extract` stub (501). Phase 2 introduces `schemas/extraction.py` and `POST /api/v1/extract`. **Decision:** migrate to the Phase 2 naming, delete the Phase 1 `extract.py` + stub route, and point the frontend `ExtractionConsole` at `/api/v1/extract`. Frontend already posts `{url, chunking, max_tokens}`; Phase 2 request fields (`render_js`, `strip_noise`, `timeout_seconds`) map cleanly.

## 1. Pydantic Schemas — `backend/schemas/extraction.py`
```python
class ExtractionRequest(BaseModel):
    url: HttpUrl                       # target page
    render_js: bool = True             # use Playwright if True
    strip_noise: bool = True           # run DOM cleaner if True
    timeout_seconds: int = 30          # ge=5, le=60

class ExtractionResponse(BaseModel):
    success: bool
    status_code: int
    execution_time_ms: float
    title: str
    raw_html: str
    clean_markdown: str
    metadata: dict[str, Any]           # source tier, final_url, token count, renderer
```
- Strict Pydantic v2, all fields described, `Field` constraints on `timeout_seconds` (5–60).
- Update `schemas/__init__.py` exports; delete `extract.py`.

## 2. Stealth Playwright Service — `backend/services/scraper.py`
- `async` module using `playwright.async_api`.
- Launch flags: `--disable-blink-features=AutomationControlled`, `--disable-dev-shm-usage`, headless.
- Randomized User-Agent from a curated rotation list; `playwright-stealth` patch applied to browser context.
- `wait_until="networkidle"` with **strict 30s cap** via `asyncio.wait_for` around the whole render; any timeout → fallback tier.
- Returns `ScrapeResult(html, final_url, status)` or raises a typed `ScraperFallbackError` on Cloudflare challenge detection, timeout, or memory exception.

## 3. Fallback Engine — `backend/services/scraper.py` (same module)
- On Playwright timeout / challenge / memory error → switch to `httpx.AsyncClient` static GET + `trafilatura` extraction (matching AGENTS.md rule 2).
- `trafilatura.extract` with `include_comments=False`, `include_tables=True`, markdown output; record `source: "static"` vs `source: "playwright"` in `metadata`.
- Markdown purity: GFM tables, preserved code blocks, alt-text retained, tracking params stripped from links.

## 4. DOM Cleaning Engine — `backend/services/cleaner.py`
- BeautifulSoup tree pruning: remove `<script>`, `<style>`, `<nav>`, `<footer>`, `<header>`, `<aside>`, `<iframe`, cookie-consent/`#CybotCookiebotDialog`/gdpr modal containers, tracking pixels/`img[src*=pixel]`, SVGs.
- Convert cleaned tree → GFM via `markdownify` (or hand-rolled traversal preserving `<pre>/<code>`, `<table>`, `alt` attributes).
- Sanitize alt-text (strip tracking query params from `src`, keep readable `alt`).

## 5. FastAPI Controller — `backend/main.py`
- `POST /api/v1/extract` → accepts `ExtractionRequest`, dispatches to scraper tiers, returns `ExtractionResponse`.
- Measured `execution_time_ms` via `time.perf_counter`; `title` from `trafilatura.extract_metadata` or `<title>`.
- BYOK headers (`X-Groq-Key` etc.) remain accepted but **never logged** (existing sanitize middleware stays).
- Migrate: remove Phase 1 `POST /extract` stub; update frontend `ExtractionConsole.tsx` to call `/api/v1/extract` with new fields.

## 6. Verification
- `curl -X POST localhost:8000/api/v1/extract -d '{"url":"https://example.com"}'` → 200 with `clean_markdown` + `metadata.source`.
- Static fallback test: point at a page that blocks headless (Cloudflare) → asserts `source: "static"`.
- Frontend: extract runs against a real page and renders Monaco output + token badge.

## Dependencies Added
`markdownify` (backend). Frontend: no new deps (schema fields already extensible).

## Out of Scope (Phase 3+)
Chunking algorithms, BYOK inference, pgvector ingestion.