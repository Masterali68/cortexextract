from fastapi import Request

from services.byok import ByokCredentials, extract_credentials, mask, strip_from_scope

SECRET = "sk-super-secret-test-key-123456"


def _make_request(headers: dict[str, str]) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/extract",
        "headers": [
            (k.lower().encode(), v.encode()) for k, v in headers.items()
        ],
        "query_string": b"",
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 1234),
    }
    return Request(scope)


def test_mask_redacts():
    assert mask(SECRET) == "sk-...456"
    assert mask("short") == "***"
    assert mask("") == ""


def test_repr_never_leaks_keys():
    creds = ByokCredentials(provider="groq", groq_key=SECRET)
    representation = repr(creds)
    assert SECRET not in representation
    assert "sk-...456" in representation


def test_extract_groq():
    request = _make_request(
        {
            "X-LLM-Provider": "groq",
            "X-Groq-Key": SECRET,
            "Content-Type": "application/json",
        }
    )
    creds = extract_credentials(request)
    assert creds.provider == "groq"
    assert creds.groq_key == SECRET
    assert creds.openai_key == ""


def test_extract_ollama_defaults():
    request = _make_request({"X-LLM-Provider": "ollama"})
    creds = extract_credentials(request)
    assert creds.provider == "ollama"
    assert creds.ollama_endpoint == "http://localhost:11434"


def test_ollama_ssrf_guard():
    request = _make_request(
        {
            "X-LLM-Provider": "ollama",
            "X-Ollama-Endpoint": "http://evil.example.com:9999",
        }
    )
    creds = extract_credentials(request)
    assert creds.ollama_endpoint == "http://localhost:11434"


def test_strip_from_scope_removes_keys():
    request = _make_request({"X-Groq-Key": SECRET, "Host": "localhost"})
    strip_from_scope(request)
    names = {name.decode().lower() for name, _ in request.scope["headers"]}
    assert "x-groq-key" not in names
    assert "host" in names
