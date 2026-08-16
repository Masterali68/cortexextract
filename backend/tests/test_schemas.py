from pydantic import ValidationError
import pytest

from schemas import (
    ChunkRequest,
    ExtractionRequest,
    ExtractionResponse,
    PipelineRequest,
    SchemaExtractRequest,
    VectorIngestRequest,
)


def test_extraction_request_defaults():
    request = ExtractionRequest(url="https://example.com")
    assert request.render_js is True
    assert request.strip_noise is True
    assert request.timeout_seconds == 30


def test_extraction_request_timeout_bounds():
    with pytest.raises(ValidationError):
        ExtractionRequest(url="https://example.com", timeout_seconds=2)
    with pytest.raises(ValidationError):
        ExtractionRequest(url="https://example.com", timeout_seconds=61)


def test_extraction_request_rejects_bad_url():
    with pytest.raises(ValidationError):
        ExtractionRequest(url="not-a-url")


def test_extraction_response_round_trip():
    payload = {
        "success": True,
        "status_code": 200,
        "execution_time_ms": 12.5,
        "title": "Example",
        "raw_html": "<html></html>",
        "clean_markdown": "# Example",
        "metadata": {"source": "static"},
    }
    response = ExtractionResponse(**payload)
    assert response.success is True


def test_chunk_request_mode_validation():
    with pytest.raises(ValidationError):
        ChunkRequest(text="x", mode="unknown")
    with pytest.raises(ValidationError):
        ChunkRequest(text="x", max_tokens=16)  # below ge=32


def test_schema_request_requires_json_schema():
    with pytest.raises(ValidationError):
        SchemaExtractRequest(markdown="x", json_schema="not-a-dict")


def test_vector_ingest_request():
    request = VectorIngestRequest(markdown="# Hi", chunk_mode="heading")
    assert request.max_tokens == 512
    assert request.title == ""


def test_pipeline_request_defaults():
    request = PipelineRequest(url="https://example.com")
    assert request.chunk_mode == "heading"
    assert request.generate_schema is True
    assert request.store_vectors is True
    assert request.timeout_seconds == 30
