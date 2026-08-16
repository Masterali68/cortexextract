Markdown
# AGENTS.md — Master Technical Guidelines for CortexExtract

## Project Vision & System Architecture
CortexExtract is an enterprise-grade, open-source AI web extraction engine and web studio. It transforms raw, script-heavy web pages into deterministic, high-density LLM context, clean Markdown, structured JSON schemas, and vector-ready embeddings.

[ Web Client (Next.js / Tailwind) ] ──(BYOK Headers)──► [ Python FastAPI Gateway ]
│
┌─────────────────────────────────────────────────────────┴────────────────────────────────────────┐
│                                                                                                  │
▼                                                                                                  ▼
[ Stealth Scraper Pipeline ]                                                          [ LLM / RAG Processing Pipeline ]
├─ Playwright (Chromium / Firefox)                                                    ├─ Semantic & Hybrid Chunking
├─ Anti-Bot / Fingerprint Evasion                                                     ├─ Structural Noise Pruning (Trafilatura)
└─ Proxy Rotation & Fingerprint Spoofing                                              └─ BYOK Inference Engine (Groq/Ollama/OpenAI)
│
▼
[ Supabase pgvector & JSON Export ]


---

## Technical Stack Specifications

- **Frontend Studio:** Next.js 14+ (App Router), TypeScript (Strict), Tailwind CSS, Framer Motion, Lucide React, Monaco Editor (`@monaco-editor/react`), Zustand (Global State).
- **Extraction & Engine Backend:** Python 3.11+, FastAPI, Pydantic v2, Playwright, Trafilatura, BeautifulSoup4, `tiktoken` (Token counting).
- **Anti-Bot & Stealth Tier:** `playwright-stealth`, Undetected Chromedriver, User-Agent rotation, Headless Canvas spoofing.
- **RAG & Chunking Core:** Recursive Character Splitting, Semantic Sentence Chunking, Token-Budgeting (256 / 512 / 1024 token windows).
- **Database & Persistence:** Supabase (PostgreSQL + `pgvector`), Redis / DragonflyDB (Rate-limiting & caching layer).
- **BYOK Architecture:** Groq API, Local Ollama (`http://localhost:11434`), OpenAI (`gpt-4o-mini`), Anthropic Claude 3.5 Sonnet.

---

## Design System Specs (Dark Slate + Vibrant Orange)

All UI elements must follow these exact design token guidelines:

- **Canvas Background:** `#09090B` (`bg-zinc-950`)
- **Card Surface & Glass Panels:** `#18181B` (`bg-zinc-900/90 border border-zinc-800/80`)
- **Primary Accent Orange:** `#FF6B00` (`bg-orange-500 hover:bg-orange-600 text-white`)
- **Accent Glows & Neon Indicators:** `shadow-[0_0_20px_rgba(255,107,0,0.25)]`
- **Monaco / Code Block Theme:** Dark Slate (`bg-zinc-900 text-orange-400/90`)
- **Active Status Badges:** `bg-orange-500/10 text-orange-400 border border-orange-500/20`

---

## Build & Execution Commands

### Frontend Studio
```bash
npm run dev          # Launch Next.js dev server on port 3000
npm run build        # Production build validation
npm run lint         # ESLint + TypeScript strict checks
Python FastAPI Extraction Engine
Bash
python -m venv venv
source venv/bin/activate || venv\Scripts\activate
pip install -r requirements.txt
playwright install --with-deps chromium firefox
uvicorn main:app --reload --host 0.0.0.0 --port 8000
Docker / Local Infrastructure
Bash
docker-compose up -d  # Spins up local Redis, Supabase pgvector, and FastAPI backend
System Engineering Rules
1. Zero-Trust BYOK (Bring Your Own Key) Security
Client-Side Storage: All API keys (Groq, OpenAI, Anthropic) MUST be stored strictly in the user's browser localStorage or session state.

Header Injection: Keys are sent to backend API routes via volatile custom HTTP headers (X-Groq-Key, X-OpenAI-Key).

Zero Logging: Backend logs MUST sanitize headers and NEVER print or record user API keys or raw bearer tokens to console/files.

2. Advanced Extraction & Noise Removal Standards
DOM Stripping: Systematically prune script tags (<script>), style sheets (<style>), SVGs, tracking pixels, cookie consent popups, modal overlays, navbars, and site footers.

Fallbacks: If dynamic Playwright rendering fails (due to Cloudflare or blocking), the pipeline MUST automatically fallback to fast static fetching (httpx + trafilatura).

Markdown Purity: Extracted Markdown must convert tables into clean GFM (GitHub Flavored Markdown) and preserve image alt-texts while removing tracking link parameters.

3. RAG & Vector Pipeline Rules
Token Budgeting: Every extraction request must return exact token metrics calculated via tiktoken (cl100k_base / o200k_base).

Chunking Controls: Support 3 distinct chunking algorithms selectable via the API/UI:

Fixed Token Window (e.g., 512 tokens with 10% overlap).

Semantic Paragraph Splitting (preserving context boundaries).

Structural Markdown Heading Splitter (#, ##, ###).

4. Code Quality & Pydantic Validation
All API request and response bodies MUST use strict Pydantic v2 schemas with detailed descriptions and input validation.

All TypeScript components must be explicitly typed—NEVER use any.

Keep API route latency below 1.5 seconds for static sites and below 4.0 seconds for heavy dynamic SPA renders.