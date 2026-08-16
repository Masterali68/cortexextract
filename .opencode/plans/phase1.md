# Phase 1 — Monorepo Scaffold & Health Baseline

## Analysis Summary
- `CortexScrape/` root currently contains **only** `AGENTS.md` (greenfield monorepo).
- AGENTS.md mandates: FastAPI extraction gateway, Next.js 14 App Router studio, BYOK zero-trust headers, Dark Slate + Vibrant Orange design tokens, Redis + Supabase pgvector infra, tiktoken token metrics.

## 1. File System Setup

```
CortexScrape/
├── AGENTS.md                     # existing master guidelines (root of truth)
├── .env.example                  # BYOK + infra vars (no secrets committed)
├── docker-compose.yml            # redis, pgvector, backend
├── backend/
│   ├── main.py                   # FastAPI app + /health + /extract route stubs
│   ├── requirements.txt
│   ├── schemas/                  # Pydantic v2 request/response models
│   │   ├── __init__.py
│   │   ├── extract.py            # ExtractRequest / ExtractResponse
│   │   └── health.py             # HealthResponse
│   └── services/
│       ├── __init__.py
│       ├── extractor/            # Playwright + trafilatura fallback (Phase 2 stubs)
│       ├── chunker/              # 3 chunking algos (Phase 2 stubs)
│       └── metrics.py            # tiktoken token counting
└── frontend/
    ├── package.json
    ├── tsconfig.json             # strict
    ├── next.config.mjs
    ├── tailwind.config.ts        # design token mapping (see §3)
    ├── postcss.config.mjs
    ├── app/
    │   ├── layout.tsx            # dark theme shell, bg-zinc-950
    │   ├── page.tsx              # studio landing
    │   └── globals.css
    ├── store/                    # Zustand global state
    │   └── extractorStore.ts
    └── components/
        ├── Header.tsx
        └── ExtractionConsole.tsx # Monaco + controls
```

## 2. Dependencies & Tooling

**Backend (`requirements.txt`):**
```
fastapi
uvicorn[standard]
playwright
playwright-stealth
trafilatura
pydantic>=2.0
tiktoken
beautifulsoup4
httpx
```
Post-install: `playwright install --with-deps chromium firefox`

**Frontend (`package.json`):**
```
next@14  react  react-dom  typescript  tailwindcss  postcss  autoprefixer
zustand  @monaco-editor/react  framer-motion  lucide-react  clsx
```
Scripts: `dev` (port 3000), `build`, `lint`.

## 3. Design Token System (`tailwind.config.ts`)
```
colors: {
  canvas:   '#09090B',   // bg-zinc-950
  panel:    '#18181B',   // bg-zinc-900/90 border-zinc-800/80
  primary:  '#FF6B00',   // orange-500 hover:orange-600
}
boxShadow: { glow: '0 0 20px rgba(255,107,0,0.25)' }
```
Expose as `bg-canvas`, `bg-panel/panel-border`, `bg-primary hover:bg-primary-600`, `shadow-glow` so AGENTS.md tokens become semantic utilities.

## 4. Dev Server Verification & Health Checks

- **`docker-compose.yml`:** `redis` (`redis:7-alpine`), `supabase/postgres:15.4` with `pgvector` extension enabled, `backend` build from `backend/`, port mapping `8000:8000`.
- **Execution:** `docker-compose up -d`, then `uvicorn main:app --reload --host 0.0.0.0 --port 8000`.
- **`GET /health`** → `{ "status": "ok", "timestamp": <ISO-8601 UTC>, "version": "0.1.0" }`, plus optional `redis`/`postgres` connectivity booleans; Pydantic v2 `HealthResponse`.
- **Verify:** `curl localhost:8000/health` → HTTP 200 + `status: ok`; `curl localhost:3000` → studio shell renders with `bg-canvas` + orange accents.
- **Security:** BYOK headers (`X-Groq-Key`, `X-OpenAI-Key`) accepted on `/extract`, never logged (zero-logging rule from AGENTS.md).

## Out of Scope (Phase 2+)
Stealth scraper pipeline, chunking algorithms, BYOK inference, pgvector ingestion.