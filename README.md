# CortexExtract

**Turn script-heavy web pages into deterministic, high-density LLM context.**

CortexExtract is an open-source AI web extraction engine and web studio. It scrapes sites that fight back, strips the noise, and produces exactly what you need to build on top of the web: clean Markdown, validated JSON schemas, token-exact statistics, and pgvector-ready embeddings — then lets you ask questions over everything it stored.

```
[ Web Studio (Next.js / Tailwind) ] ──(BYOK headers)──► [ Python FastAPI Gateway ]
                                                            │
                    ┌───────────────────────────────────────┴────────────────────────┐
                    ▼                                                                  ▼
        [ Stealth Scraper Pipeline ]                                    [ LLM / RAG Processing Pipeline ]
        ├─ Playwright (Chromium) + playwright-stealth                    ├─ JSON-schema extraction (BYOK)
        ├─ Tiered fallback → static httpx + Trafilatura                  ├─ Chunking: fixed / semantic / heading
        └─ Noise pruning (nav, footer, consent popups, ads)              └─ RAG Ask with hybrid retrieval
                    │                                                                  │
                    ▼                                                                  ▼
        [ Supabase / PostgreSQL + pgvector ]  ⇐  [ Redis cache & rate limiting ]
```

## Highlights

- **Stealth extraction** — Playwright with anti-bot fingerprint evasion, JS-button link discovery, lazy-load handling, and automatic fallback to fast static fetching when a site blocks headless browsing.
- **Noise removal done right** — prunes scripts, navbars, footers, cookie popups, modals, and ad frames, while **preserving contact info** (emails, phones) that lives in those stripped regions so "what's the email?" still works.
- **Deterministic, token-exact output** — every extraction returns character/word counts and exact token metrics (`cl100k_base` / `o200k_base`) via `tiktoken`.
- **Three chunking algorithms** — fixed token window (with overlap), semantic paragraph splits, and structural heading splits, each lossless.
- **Whole-site crawl** — discovers an index from `llms.txt` or `sitemap.xml`, follows cross-page links, and fetches `.md` files directly without a browser.
- **BYOK AI** — bring your own key (Groq, OpenAI, or local Ollama). Keys stay in your browser's `localStorage` and travel via per-request headers; the backend never logs or stores them.
- **RAG Ask** — answer questions over scraped content with hybrid keyword + vector retrieval, grounded citations, and a balanced "answer or admit you don't know" model prompt.
- **Vector storage** — idempotent chunk upserts into PostgreSQL with `pgvector`, section-aware metadata, and instant health metrics.

## Architecture

| Layer | Stack |
| --- | --- |
| Web Studio | Next.js 14 (App Router), TypeScript (strict), Tailwind CSS, Zustand, Monaco Editor, Framer Motion |
| Extraction Engine | Python 3.11+, FastAPI, Playwright + `playwright-stealth`, Trafilatura, BeautifulSoup4, `markdownify` |
| RAG & Chunking | Recursive/semantic/heading chunkers, token budgeting via `tiktoken` |
| Data & Cache | PostgreSQL + `pgvector`, Redis (extraction cache + rate limiting) |
| Inference (BYOK) | Groq, OpenAI, Anthropic-ready, or local Ollama |

## Prerequisites

- **Python 3.11+** and **Node.js 18+**
- **Ollama** running locally (`http://localhost:11434`) for chat + embeddings — the engine auto-selects the best local model and uses `nomic-embed-text` for vector search (pull it with `ollama pull nomic-embed-text`). Alternatively, supply an OpenAI key per-request and embeddings run through OpenAI.
- **PostgreSQL with pgvector** — the easiest path is `docker-compose up -d`; you can also point `DATABASE_URL` at any existing pgvector-enabled Postgres.
- **Redis** for the extraction cache and rate limiting.

## Quickstart

### 1. Spin up the infrastructure

```bash
docker-compose up -d        # Redis, pgvector, and the FastAPI backend
```

### 2. Run the backend locally

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
playwright install --with-deps chromium
cp ../.env.example .env
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Run the web studio

```bash
cd frontend
npm install
npm run dev                 # http://localhost:3000
```

Point the studio at `http://localhost:3000`, paste a URL, pick **Single Page** or **Whole Site**, and hit **Extract All**.

## Environment

Copy `.env.example` to `.env`. All BYOK API keys are optional at startup — they are supplied per-request via `X-Groq-Key` / `X-OpenAI-Key` headers.

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql://postgres:postgres@localhost:54322/postgres` | pgvector database |
| `REDIS_URL` | `redis://localhost:6379/0` | cache + rate limiting |
| `OLLAMA_ENDPOINT` | `http://localhost:11434` | local inference + embeddings |
| `DEV_ORIGINS` | `http://localhost:3000` | CORS allowlist |
| `PROXY_URLS` | *(empty)* | comma-separated stealth proxy rotation |
| `EXTRACT_CACHE_TTL` | `300` | extraction cache TTL (seconds) |

## API

`/api/v1/...` — all bodies are strict Pydantic v2 models.

| Endpoint | Purpose |
| --- | --- |
| `POST /extract` | Scrape a single page → clean GFM Markdown + token metrics |
| `POST /pipeline` | Extract + chunk + embed + upsert vectors (+ optional JSON schema) |
| `POST /crawl` | Recursively crawl a site, with `llms.txt` / `sitemap.xml` index discovery |
| `POST /ask` | RAG question-answering over stored chunks (hybrid retrieval, top-k) |
| `POST /schema` | LLM JSON-schema extraction from markdown |
| `POST /chunk` | Chunk text with fixed / semantic / heading algorithms |
| `POST /vector` | Chunk + embed + upsert arbitrary markdown |
| `POST /vector/search` | Vector similarity search over stored documents |

## Security model

- **Zero-trust BYOK**: keys are stored client-side, sent via volatile request headers, never logged, and never persisted by the backend.
- **Prompt-injection hardening**: retrieved web content is treated as untrusted data — delimited, escaped, and confined to the user turn; instructions live only in the system prompt.
- **SSRF guard**: outbound fetches block private/link-local networks; Ollama is pinned to the loopback interface.
- **Rate limiting**: 30 requests/minute per IP on AI endpoints.

## Design system

Dark slate + vibrant orange. Canvas `#09090B`, glass panels `#18181B`, primary accent `#FF6B00`, glow `rgba(255,107,0,0.25)`, Monaco dark-slate code theme.

## Testing

```bash
cd backend
source venv/bin/activate
python -m pytest tests -q      # 74 tests: cleaner, crawler, chunker, ask, schemas, pipeline
```

```bash
cd frontend
npx tsc --noEmit && npm run lint && npm run build
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the dev workflow, test conventions, and the zero-trust BYOK security rules every contribution must respect.

## Roadmap

- [x] Stealth scraper with tiered fallback + JS-button link discovery
- [x] Noise pruning with contact-info preservation
- [x] Whole-site crawl via `llms.txt` / `sitemap.xml` + markdown-direct fetch
- [x] Hybrid retrieval RAG Ask
- [ ] LLM-powered schema suggestions
- [ ] Batch URL ingestion
- [ ] Embedding provider abstraction beyond Ollama/OpenAI

## License

MIT
