import httpx
import pytest
from fastapi import HTTPException
from app.config import settings
from app.providers.apollo import ApolloProvider
from app.providers.serpapi import SerpAPIProvider
from app.providers.ai import CompatibleAI


def transport(monkeypatch, handler):
    original = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kw: original(transport=httpx.MockTransport(handler), **kw),
    )


def test_live_failures_are_visible(monkeypatch):
    monkeypatch.setattr(settings, "apollo_api_key", "test-only")
    transport(monkeypatch, lambda r: httpx.Response(403, json={"error": "no access"}))
    with pytest.raises(HTTPException) as exc:
        ApolloProvider().enrich({"provider_id": "123"})
    assert exc.value.status_code == 502 and "No mock fallback" in exc.value.detail


def test_serpapi_preserves_source_and_bounds(monkeypatch):
    monkeypatch.setattr(settings, "serpapi_api_key", "test-only")
    transport(
        monkeypatch,
        lambda r: httpx.Response(
            200,
            json={
                "organic_results": [
                    {
                        "title": "Profile",
                        "link": "https://firm.example/bio",
                        "snippet": "Jane, analyst",
                    }
                ]
                * 10
            },
        ),
    )
    rows = SerpAPIProvider().search(
        {"name": "Jane", "company": "Firm", "title": "Analyst"}
    )
    assert (
        len(rows) == 3
        and rows[0]["kind"] == "unverified_lead"
        and rows[0]["url"] == "https://firm.example/bio"
    )


def test_ai_contract_and_malformed_response(monkeypatch):
    import json

    monkeypatch.setattr(settings, "ai_api_key", "test-only")

    def handle(req):
        body = json.loads(req.content)
        assert (
            req.url.path.endswith("/chat/completions")
            and body["response_format"]["type"] == "json_object"
        )
        assert "UNTRUSTED" in body["messages"][0]["content"]
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "not json"}}]}
        )

    transport(monkeypatch, handle)
    with pytest.raises(HTTPException) as exc:
        CompatibleAI().complete("generate", {})
    assert exc.value.status_code == 502
