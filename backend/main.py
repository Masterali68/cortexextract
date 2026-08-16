from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware

from schemas import (
    AskRequest,
    AskResponse,
    ChunkRequest,
    ChunkResponse,
    ExtractionRequest,
    ExtractionResponse,
    HealthResponse,
    PipelineRequest,
    PipelineResponse,
    PipelineStats,
    SchemaMeta,
    VectorResult,
    SchemaExtractRequest,
    SchemaExtractResponse,
    CrawlRequest,
    CrawlResponse,
    VectorIngestRequest,
    VectorIngestResponse,
    VectorSearchRequest,
    VectorSearchResponse,
)
from services.byok import extract_credentials, strip_from_scope
from services.chunker import chunk, heading_path, strip_boilerplate
from services.cleaner import DomCleaner, extract_title
from services.crawler import crawl_site
from services.embeddings import EmbeddingsError, embed_texts
from services.llm import LlmProviderError, run_question_answer, run_schema_extraction
from services.rate_limit import check_rate_limit
from services.redis_client import cache_get, cache_set, ping as redis_ping
from services.scraper import ScraperFallbackError, scrape_page
from services.token_counter import compute_stats
from services import vector_store

APP_VERSION = os.getenv("APP_VERSION", "0.5.0")
EXTRACT_CACHE_TTL = int(os.getenv("EXTRACT_CACHE_TTL", "300"))
_DEFAULT_ORIGINS = ["http://localhost:3000"]
DEV_ORIGINS = [
    origin.strip()
    for origin in os.getenv("DEV_ORIGINS", ",".join(_DEFAULT_ORIGINS)).split(",")
    if origin.strip()
]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cortexextract")

@asynccontextmanager
async def lifespan(_: FastAPI):
    """Ensure the pgvector schema exists before serving traffic."""
    try:
        await vector_store.ensure_schema()
    except vector_store.VectorStoreError:
        logger.warning("pgvector schema init deferred (infra unavailable at startup)")
    yield

app = FastAPI(
    title="CortexExtract Gateway",
    version=APP_VERSION,
    description="FastAPI extraction gateway for the CortexExtract web studio.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=DEV_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_cleaner = DomCleaner()


@app.middleware("http")
async def byok_interceptor(request: Request, call_next):
    """Capture BYOK credentials into request.state, then zero-log them from scope."""
    request.state.byok = extract_credentials(request)
    strip_from_scope(request)
    return await call_next(request)


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    """Per-IP rate limit on mutating routes (graceful when Redis is down)."""
    if request.method in {"POST", "PUT", "DELETE", "PATCH"}:
        client_ip = request.client.host if request.client else "unknown"
        allowed, retry_after = await check_rate_limit(client_ip)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(retry_after)},
            )
    return await call_next(request)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness probe. Returns status, timestamp, version, and infra connectivity."""
    redis_ok = await redis_ping()
    postgres_ok = False
    document_count = 0
    try:
        document_count = await vector_store.count_documents()
        postgres_ok = True
    except vector_store.VectorStoreError:
        postgres_ok = False

    return HealthResponse(
        status="ok",
        timestamp=datetime.now(timezone.utc),
        version=APP_VERSION,
        redis=redis_ok,
        postgres=postgres_ok,
    )


@app.post("/api/v1/extract", response_model=ExtractionResponse)
async def extract(payload: ExtractionRequest) -> ExtractionResponse:
    """Extract a page into clean GFM markdown with exact token metrics."""
    started = time.perf_counter()
    url = str(payload.url)

    cache_key = hashlib.sha256(
        json.dumps(
            {
                "url": url,
                "render_js": payload.render_js,
                "strip_noise": payload.strip_noise,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    cached = await cache_get(f"extract:{cache_key}")
    if cached is not None:
        cached_body = json.loads(cached)
        logger.info("cache hit for %s", url)
        return ExtractionResponse(**cached_body)

    try:
        result = await scrape_page(
            url=url,
            render_js=payload.render_js,
            timeout_seconds=payload.timeout_seconds,
        )
    except ScraperFallbackError as exc:
        logger.warning("extraction failed for %s: %s", url, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Extraction failed: {exc}",
        ) from exc

    raw_html = result.html
    clean_markdown = _cleaner.clean(raw_html, strip_noise=payload.strip_noise)

    title = ""
    if result.content_metadata and result.content_metadata.get("title"):
        title = result.content_metadata["title"]
    if not title:
        title = extract_title(raw_html)

    stats = compute_stats(clean_markdown)

    metadata = {
        "source": result.source,
        "final_url": result.final_url,
        "renderer": "playwright" if result.source == "playwright" else "httpx+trafilatura",
        "characters": stats.characters,
        "words": stats.words,
        "tokens_cl100k": stats.tokens_cl100k,
        "tokens_o200k": stats.tokens_o200k,
        "strip_noise": payload.strip_noise,
        "content_score": (result.content_metadata or {}).get("content_score", 0),
        "discovered_links": (result.content_metadata or {}).get("discovered_links", []),
    }

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    logger.info(
        "extracted %s source=%s status=%d %.0fms tokens=%d",
        url,
        result.source,
        result.status_code,
        elapsed_ms,
        stats.tokens_cl100k,
    )

    response = ExtractionResponse(
        success=True,
        status_code=result.status_code,
        execution_time_ms=round(elapsed_ms, 2),
        title=title,
        raw_html=raw_html,
        clean_markdown=clean_markdown,
        metadata=metadata,
    )
    await cache_set(
        f"extract:{cache_key}",
        response.model_dump_json(),
        EXTRACT_CACHE_TTL,
    )
    return response


@app.post("/api/v1/chunk", response_model=ChunkResponse)
async def chunk_text(payload: ChunkRequest) -> ChunkResponse:
    """Chunk text using fixed-window, semantic, or heading-split algorithms."""
    chunks = chunk(
        payload.text,
        mode=payload.mode,
        max_tokens=payload.max_tokens,
        overlap=payload.overlap,
    )
    stats = compute_stats(payload.text)
    return ChunkResponse(
        mode=payload.mode,
        max_tokens=payload.max_tokens,
        chunks=[
            {
                "content": c.content,
                "start": c.start,
                "end": c.end,
                "token_count": c.token_count,
            }
            for c in chunks
        ],
        stats={
            "characters": stats.characters,
            "words": stats.words,
            "tokens_cl100k": stats.tokens_cl100k,
            "tokens_o200k": stats.tokens_o200k,
            "total_chunks": len(chunks),
        },
    )


@app.post("/api/v1/schema", response_model=SchemaExtractResponse)
async def schema_extract(
    payload: SchemaExtractRequest,
    request: Request,
) -> SchemaExtractResponse:
    """Send clean markdown to the BYOK LLM provider and return validated JSON."""
    byok = request.state.byok
    try:
        data, provider, model, usage = await run_schema_extraction(
            byok=byok,
            markdown=payload.markdown,
            json_schema=payload.json_schema,
            max_tokens=payload.max_tokens,
        )
    except LlmProviderError as exc:
        logger.warning("schema extraction failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return SchemaExtractResponse(
        success=True,
        data=data,
        provider=provider,
        model=model,
        usage=usage,
    )


@app.post("/api/v1/vector", response_model=VectorIngestResponse)
async def vector_ingest(
    payload: VectorIngestRequest,
    request: Request,
) -> VectorIngestResponse:
    """Chunk markdown, embed it, and upsert the vectors into pgvector."""
    byok = request.state.byok
    provider = "ollama" if byok.provider != "openai" else "openai"
    api_key = byok.openai_key if provider == "openai" else ""

    try:
        await vector_store.ensure_schema()
        chunks = chunk(
            payload.markdown,
            mode=payload.chunk_mode,
            max_tokens=payload.max_tokens,
            overlap=0.1,
        )
        texts = [c.content for c in chunks]
        vectors = await embed_texts(
            texts,
            provider=provider,
            api_key=api_key,
            endpoint=byok.ollama_endpoint,
        )
    except (EmbeddingsError, vector_store.VectorStoreError) as exc:
        logger.warning("vector ingest failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    documents = [
        vector_store.Document(
            source_url=payload.source_url,
            title=payload.title,
            content=chunk_item.content,
            token_count=chunk_item.token_count,
            embedding=vector,
            metadata={"chunk_index": idx},
        )
        for idx, (chunk_item, vector) in enumerate(zip(chunks, vectors))
    ]

    inserted = await vector_store.upsert_documents(documents)
    total = await vector_store.count_documents()
    return VectorIngestResponse(
        success=True,
        inserted=inserted,
        total_documents=total,
        provider=provider,
    )


@app.post("/api/v1/vector/search", response_model=VectorSearchResponse)
async def vector_search(
    payload: VectorSearchRequest,
    request: Request,
) -> VectorSearchResponse:
    """Embed a query and return the top-k matching chunks."""
    byok = request.state.byok
    provider = "ollama" if byok.provider != "openai" else "openai"
    api_key = byok.openai_key if provider == "openai" else ""

    try:
        await vector_store.ensure_schema()
        (query_vector,) = await embed_texts(
            [payload.query],
            provider=provider,
            api_key=api_key,
            endpoint=byok.ollama_endpoint,
        )
        hits = await vector_store.search(query_vector, top_k=payload.top_k)
    except (EmbeddingsError, vector_store.VectorStoreError) as exc:
        logger.warning("vector search failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return VectorSearchResponse(
        success=True,
        provider=provider,
        results=[
            {
                "content": hit.content,
                "source_url": hit.source_url,
                "title": hit.title,
                "score": hit.score,
                "token_count": hit.token_count,
            }
            for hit in hits
        ],
    )


@app.post("/api/v1/ask", response_model=AskResponse)
async def ask_question(
    payload: AskRequest,
    request: Request,
) -> AskResponse:
    """Retrieve the most relevant chunks, then answer the question via the BYOK provider.

    The retrieved chunks are treated as untrusted data: instructions never
    appear in them and the system prompt hard-isolates them from control flow.
    """
    byok = request.state.byok
    provider = byok.provider or "ollama"
    embed_provider = "ollama" if provider != "openai" else "openai"
    api_key = byok.openai_key if embed_provider == "openai" else ""

    try:
        await vector_store.ensure_schema()
        (query_vector,) = await embed_texts(
            [payload.question],
            provider=embed_provider,
            api_key=api_key,
            endpoint=byok.ollama_endpoint,
        )
        hits = await vector_store.search(query_vector, top_k=max(payload.top_k * 4, 20))
        hits = vector_store.rerank_hybrid(payload.question, hits, payload.top_k)
    except (EmbeddingsError, vector_store.VectorStoreError) as exc:
        logger.warning("ask retrieval failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Retrieval failed: {exc}",
        ) from exc

    if not hits:
        return AskResponse(
            success=True,
            question=payload.question,
            answer="I don't have enough context to answer that. Extract All first to store chunks.",
            sources=[],
            provider=provider,
            model="",
            usage={},
        )

    try:
        answer, provider_used, model, usage = await run_question_answer(
            byok=byok,
            question=payload.question,
            context_chunks=[hit.content for hit in hits],
            max_tokens=payload.max_tokens,
        )
    except LlmProviderError as exc:
        logger.warning("ask answer failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    logger.info(
        "asked provider=%s model=%s sources=%d",
        provider_used,
        model,
        len(hits),
    )
    return AskResponse(
        success=True,
        question=payload.question,
        answer=answer,
        sources=[
            {
                "content": hit.content,
                "title": hit.title,
                "source_url": hit.source_url,
                "score": hit.score,
                "token_count": hit.token_count,
            }
            for hit in hits
        ],
        provider=provider_used,
        model=model,
        usage=usage,
    )


_DEFAULT_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "headings": {"type": "array", "items": {"type": "string"}},
        "key_points": {"type": "array", "items": {"type": "string"}},
        "links": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "summary", "headings", "key_points"],
}


@app.post("/api/v1/pipeline", response_model=PipelineResponse)
async def pipeline_extract(
    payload: PipelineRequest,
    request: Request,
) -> PipelineResponse:
    """One-shot: extract → clean → chunk → optionally schema + vector store.

    Extraction failure aborts the pipeline. Schema and vector-store steps are
    best-effort: their failures are reported in the response, never fatal.
    """
    started = time.perf_counter()
    url = str(payload.url)
    byok = request.state.byok
    provider = byok.provider or "ollama"
    embed_provider = "ollama" if provider != "openai" else "openai"
    api_key = byok.openai_key if embed_provider == "openai" else ""

    cache_key = hashlib.sha256(
        json.dumps(
            {"url": url, "render_js": payload.render_js, "strip_noise": payload.strip_noise},
            sort_keys=True,
        ).encode()
    ).hexdigest()
    cached = await cache_get(f"extract:{cache_key}")
    if cached is not None:
        cached_body = json.loads(cached)
        result = cached_body
        raw_html = result["raw_html"]
        clean_markdown = result["clean_markdown"]
        title = result["title"]
        metadata = result["metadata"]
    else:
        try:
            scrape = await scrape_page(
                url=url,
                render_js=payload.render_js,
                timeout_seconds=payload.timeout_seconds,
            )
        except ScraperFallbackError as exc:
            logger.warning("pipeline extraction failed for %s: %s", url, exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Extraction failed: {exc}",
            ) from exc

        raw_html = scrape.html
        clean_markdown = _cleaner.clean(raw_html, strip_noise=payload.strip_noise)
        title = ""
        if scrape.content_metadata and scrape.content_metadata.get("title"):
            title = scrape.content_metadata["title"]
        if not title:
            title = extract_title(raw_html)

        stats = compute_stats(clean_markdown)
        metadata = {
            "source": scrape.source,
            "final_url": scrape.final_url,
            "renderer": "playwright" if scrape.source == "playwright" else "httpx+trafilatura",
            "characters": stats.characters,
            "words": stats.words,
            "tokens_cl100k": stats.tokens_cl100k,
            "tokens_o200k": stats.tokens_o200k,
            "strip_noise": payload.strip_noise,
            "content_score": (scrape.content_metadata or {}).get("content_score", 0),
            "discovered_links": (scrape.content_metadata or {}).get("discovered_links", []),
        }
        await cache_set(
            f"extract:{cache_key}",
            json.dumps(
                {
                    "raw_html": raw_html,
                    "clean_markdown": clean_markdown,
                    "title": title,
                    "metadata": metadata,
                }
            ),
            EXTRACT_CACHE_TTL,
        )

    stats = compute_stats(clean_markdown)
    chunks = chunk(
        clean_markdown,
        mode=payload.chunk_mode,
        max_tokens=payload.chunk_max_tokens,
        overlap=0.1,
    )

    vector_result: VectorResult | None = None
    if payload.store_vectors:
        try:
            await vector_store.ensure_schema()
            vector_markdown = strip_boilerplate(clean_markdown)
            vector_chunks = chunk(
                vector_markdown,
                mode=payload.chunk_mode,
                max_tokens=payload.chunk_max_tokens,
                overlap=0.1,
            )
            vectors = await embed_texts(
                [c.content for c in vector_chunks],
                provider=embed_provider,
                api_key=api_key,
                endpoint=byok.ollama_endpoint,
            )
            documents = [
                vector_store.Document(
                    source_url=url,
                    title=title,
                    content=c.content,
                    token_count=c.token_count,
                    embedding=vector,
                    metadata={
                        "chunk_index": idx,
                        "section": heading_path(c.content),
                    },
                )
                for idx, (c, vector) in enumerate(zip(vector_chunks, vectors))
            ]
            inserted = await vector_store.upsert_documents(documents)
            total = await vector_store.count_documents()
            vector_result = VectorResult(
                stored=True, inserted=inserted, total_documents=total, error=None
            )
        except (EmbeddingsError, vector_store.VectorStoreError) as exc:
            logger.warning("pipeline vector step failed: %s", exc)
            vector_result = VectorResult(stored=False, inserted=0, total_documents=0, error=str(exc))

    schema_result: dict[str, Any] | None = None
    schema_meta: SchemaMeta | None = None
    if payload.generate_schema:
        try:
            schema_data, schema_provider, schema_model, _ = await asyncio.wait_for(
                run_schema_extraction(
                    byok=byok,
                    markdown=clean_markdown,
                    json_schema=_DEFAULT_JSON_SCHEMA,
                    max_tokens=payload.schema_max_tokens,
                ),
                timeout=150,
            )
            schema_result = schema_data
            schema_meta = SchemaMeta(provider=schema_provider, model=schema_model, error=None)
        except LlmProviderError as exc:
            logger.warning("pipeline schema step failed: %s", exc)
            schema_meta = SchemaMeta(provider=provider, model=None, error=str(exc))
        except asyncio.TimeoutError:
            logger.warning("pipeline schema step timed out after 150s")
            schema_meta = SchemaMeta(provider=provider, model=None, error="Schema generation timed out (150s)")

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    logger.info(
        "pipeline %s source=%s chunks=%d schema=%s vector=%s %.0fms",
        url,
        metadata.get("source"),
        len(chunks),
        "yes" if schema_result else "no",
        "yes" if vector_result and vector_result.stored else "no",
        elapsed_ms,
    )

    return PipelineResponse(
        success=True,
        execution_time_ms=round(elapsed_ms, 2),
        title=title,
        metadata=metadata,
        clean_markdown=clean_markdown,
        raw_html=raw_html,
        stats=PipelineStats(
            characters=stats.characters,
            words=stats.words,
            tokens_cl100k=stats.tokens_cl100k,
            tokens_o200k=stats.tokens_o200k,
        ),
        chunks=[{"content": c.content, "start": c.start, "end": c.end, "token_count": c.token_count} for c in chunks],
        schema_output=schema_result,
        schema_meta=schema_meta,
        vector=vector_result,
    )


@app.post("/api/v1/crawl", response_model=CrawlResponse)
async def crawl_endpoint(payload: CrawlRequest, request: Request) -> CrawlResponse:
    """Crawl the same-origin site reachable from `url` and store every page.

    BFS over discovered navigation links (including JS button links), with the
    smart scraper (retries, tier comparison, lazy-load scroll) per page. Chunks
    are embedded and upserted idempotently. Per-page failures are reported, not
    fatal.
    """
    byok = request.state.byok
    provider = byok.provider or "ollama"
    embed_provider = "ollama" if provider != "openai" else "openai"
    api_key = byok.openai_key if embed_provider == "openai" else ""
    started = time.perf_counter()
    try:
        result = await crawl_site(
            url=payload.url,
            max_pages=payload.max_pages,
            max_depth=payload.max_depth,
            render_js=payload.render_js,
            timeout_seconds=payload.timeout_seconds,
            strip_noise=payload.strip_noise,
            chunk_mode=payload.chunk_mode,
            chunk_max_tokens=payload.chunk_max_tokens,
            store_vectors=payload.store_vectors,
            embed_provider=embed_provider,
            api_key=api_key,
            ollama_endpoint=byok.ollama_endpoint,
            use_index=payload.use_index,
        )
    except ScraperFallbackError as exc:
        logger.warning("crawl failed for %s: %s", payload.url, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Crawl failed: {exc}",
        ) from exc

    result["success"] = True
    result["seed_url"] = payload.url
    result["elapsed_ms"] = round((time.perf_counter() - started) * 1000.0, 2)
    logger.info(
        "crawl seed=%s pages=%d chunks=%d failures=%d",
        payload.url,
        result["pages_crawled"],
        result["chunks_stored"],
        len(result["failures"]),
    )
    return CrawlResponse(**result)