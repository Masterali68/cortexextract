from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import psycopg
from pgvector.psycopg import register_vector_async

logger = logging.getLogger("cortexextract.vector")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:54322/postgres",
)
VECTOR_DIM = int(os.getenv("VECTOR_DIM", "768"))


class VectorStoreError(Exception):
    """Raised when the pgvector store is unavailable or a query fails."""


@dataclass
class Document:
    source_url: str
    title: str
    content: str
    token_count: int
    embedding: list[float]
    metadata: dict[str, Any]


@dataclass
class SearchHit:
    content: str
    source_url: str
    title: str
    score: float
    token_count: int


async def _connect():
    try:
        connection = await psycopg.AsyncConnection.connect(DATABASE_URL, autocommit=True)
    except Exception as exc:
        raise VectorStoreError(f"Cannot connect to pgvector: {exc}") from exc
    await register_vector_async(connection)
    return connection


async def ensure_schema() -> None:
    """Create the vector extension and documents table if missing."""
    connection = await _connect()
    try:
        await connection.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS documents (
                id BIGSERIAL PRIMARY KEY,
                source_url TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL,
                token_count INT NOT NULL DEFAULT 0,
                metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                embedding vector({VECTOR_DIM}),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        await connection.execute(
            "DROP INDEX IF EXISTS documents_embedding_idx"
        )
        await connection.execute(
            "CREATE INDEX IF NOT EXISTS documents_embedding_idx "
            "ON documents USING hnsw (embedding vector_cosine_ops)"
        )
        await connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS documents_source_chunk_uniq "
            "ON documents (source_url, (metadata->>'chunk_index'))"
        )
    except Exception as exc:
        raise VectorStoreError(f"Schema init failed: {exc}") from exc
    finally:
        await connection.close()


async def upsert_documents(documents: list[Document]) -> int:
    """Insert documents with embeddings. Idempotent: re-inserting the same
    (source_url, chunk_index) skips the duplicate. Returns rows actually inserted."""
    connection = await _connect()
    inserted = 0
    try:
        for doc in documents:
            cursor = await connection.execute(
                """
                INSERT INTO documents (source_url, title, content, token_count, metadata, embedding, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_url, (metadata->>'chunk_index')) DO NOTHING
                """,
                (
                    doc.source_url,
                    doc.title,
                    doc.content,
                    doc.token_count,
                    psycopg.types.json.Jsonb(doc.metadata),
                    doc.embedding,
                    datetime.now(timezone.utc),
                ),
            )
            inserted += cursor.rowcount
        return inserted
    except Exception as exc:
        raise VectorStoreError(f"Upsert failed: {exc}") from exc
    finally:
        await connection.close()


async def search(query_vector: list[float], top_k: int = 5) -> list[SearchHit]:
    """Cosine-similarity search over stored documents."""
    connection = await _connect()
    try:
        rows = await connection.execute(
            """
            SELECT content, source_url, title, token_count,
                   1 - (embedding <=> %s::vector) AS score
            FROM documents
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (query_vector, query_vector, top_k),
        )
        results = await rows.fetchall()
    except Exception as exc:
        raise VectorStoreError(f"Search failed: {exc}") from exc
    finally:
        await connection.close()

    return [
        SearchHit(
            content=row[0],
            source_url=row[1],
            title=row[2] or "",
            score=round(float(row[4]), 4),
            token_count=int(row[3]),
        )
        for row in results
    ]


async def count_documents() -> int:
    """Total documents stored (for health checks)."""
    connection = await _connect()
    try:
        rows = await connection.execute("SELECT count(*) FROM documents")
        return int((await rows.fetchone())[0])
    except Exception as exc:
        raise VectorStoreError(f"Count failed: {exc}") from exc
    finally:
        await connection.close()


_ASK_STOPWORDS = {
    "a", "an", "and", "are", "at", "be", "can", "could", "did", "do", "does",
    "for", "from", "get", "give", "has", "have", "how", "i", "in", "is", "it",
    "its", "know", "me", "my", "of", "on", "or", "please", "should", "some",
    "such", "tell", "that", "the", "these", "this", "those", "to", "was",
    "were", "what", "when", "where", "which", "who", "why", "will", "with",
    "would", "you", "your",
}


def rerank_hybrid(question: str, hits: list[SearchHit], top_k: int) -> list[SearchHit]:
    """Blend lexical keyword matches into pure vector ranking.

    Vector-only retrieval can miss a chunk containing the exact term a user
    asked about (e.g. "email") when embedding similarity is low. Chunks sharing
    query keywords get a similarity bonus so exact-term answers surface without
    abandoning the vector signal entirely.
    """
    keywords = [
        token
        for token in re.findall(r"[a-z0-9]+", question.lower())
        if len(token) >= 3 and token not in _ASK_STOPWORDS
    ]
    if not keywords:
        return hits[:top_k]
    keyword_set = set(keywords)

    def combined(hit: SearchHit) -> float:
        content = hit.content.lower()
        matches = sum(1 for keyword in keyword_set if keyword in content)
        return hit.score + (matches / len(keyword_set)) * 0.4

    return sorted(hits, key=combined, reverse=True)[:top_k]