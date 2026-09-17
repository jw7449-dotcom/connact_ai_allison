import httpx
import pytest
from app.config import settings
from app.providers.base import _calls
from app.providers.linkedin import linkedin_profile


@pytest.fixture
def upstream(monkeypatch):
    _calls.clear()
    monkeypatch.setattr(settings, "people_mode", "live")
    monkeypatch.setattr(settings, "public_search_mode", "live")
    monkeypatch.setattr(settings, "serpapi_api_key", "test-only")
    monkeypatch.setattr(settings, "apollo_api_key", "test-only")
    calls = []
    reply = {
        "person": {
            "name": "Jane Doe",
            "linkedin_url": "https://uk.linkedin.com/in/jane-doe/",
            "email": "jane@firm.example",
            "email_status": "verified",
            "title": "Analyst",
            "organization": {"name": "Actual Firm"},
        }
    }
    original = httpx.Client

    def handle(req):
        calls.append(req)
        if req.url.host == "serpapi.com":
            assert req.url.params["engine"] == "google"
            if "start" not in req.url.params:
                return httpx.Response(
                    200,
                    json={
                        "organic_results": [
                            {
                                "title": "Firm biography",
                                "link": "https://firm.example/jane",
                                "snippet": "Additional public source",
                            }
                        ]
                    },
                )
            assert req.url.params["q"].startswith("site:linkedin.com/in/")
            return httpx.Response(
                200,
                json={
                    "organic_results": [
                        {
                            "title": "Jane Doe - Analyst | LinkedIn",
                            "link": "https://uk.linkedin.com/in/jane-doe/?trk=google",
                            "snippet": "Original search evidence",
                        },
                        {
                            "title": "Duplicate",
                            "link": "https://www.linkedin.com/in/jane-doe",
                        },
                        {
                            "title": "Company",
                            "link": "https://www.linkedin.com/company/firm",
                        },
                        {
                            "title": "Spoof",
                            "link": "https://linkedin.com.evil.example/in/person",
                        },
                    ],
                    "search_information": {"total_results": 400},
                    "serpapi_pagination": {
                        "next": "https://serpapi.com/search.json?start=10"
                    },
                },
            )
        assert req.url.host == "api.apollo.io"
        assert req.url.path == "/api/v1/people/match"
        body = req.url.params
        assert body["linkedin_url"] == "https://www.linkedin.com/in/jane-doe"
        assert "id" not in body
        assert (
            body["reveal_personal_emails"] == "false"
            and body["reveal_phone_number"] == "false"
        )
        return httpx.Response(reply.get("status", 200), json=reply)

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kw: original(transport=httpx.MockTransport(handle), **kw),
    )
    return calls, reply


def discover(client):
    response = client.post("/api/finance/search", json={"company": "Filter Only Firm"})
    assert response.status_code == 200, response.text
    return response.json()


def test_google_then_apollo_same_contact_and_cache(client, upstream):
    calls, _ = upstream
    result = discover(client)
    assert len(result["items"]) == 1
    assert result["has_more"] and result["total_is_estimate"]
    c = result["items"][0]
    assert len(calls) == 1 and calls[0].url.host == "serpapi.com"
    assert c["provider"] == "serpapi" and c["email"] == ""
    assert c["company"] == c["location"] == ""
    assert c["sources"][0]["snippet"] == "Original search evidence"
    assert c["sources"][0]["kind"] == "discovery"
    response = client.post(f'/api/contacts/{c["id"]}/enrich')
    assert response.status_code == 200, response.text
    enriched = response.json()["contact"]
    assert enriched["id"] == c["id"] and enriched["provider_id"] == c["provider_id"]
    assert enriched["email"] == "jane@firm.example"
    assert enriched["company"] == "Actual Firm"
    assert {(s["provider"], s["kind"]) for s in enriched["sources"]} == {
        ("serpapi", "discovery"),
        ("apollo", "enrichment"),
    }
    assert client.post(f'/api/contacts/{c["id"]}/enrich').json()["cached"]
    assert len(calls) == 2
    again = discover(client)["items"][0]
    assert again["id"] == c["id"] and again["email"] == enriched["email"]
    client.put(
        f'/api/contacts/{c["id"]}',
        json={
            "name": "Jane Doe",
            "company": "Edited Firm",
            "profile_url": c["profile_url"],
        },
    )
    assert not client.post(f'/api/contacts/{c["id"]}/enrich').json()["cached"]


@pytest.mark.parametrize(
    "profile,confidence",
    [
        ("https://www.linkedin.com/in/someone-else", "high"),
        (None, "high"),
        ("https://www.linkedin.com/in/jane-doe", "low"),
    ],
)
def test_identity_conflict_never_attaches_email(client, upstream, profile, confidence):
    calls, reply = upstream
    reply["person"]["linkedin_url"] = profile
    reply["match_confidence"] = confidence
    c = discover(client)["items"][0]
    response = client.post(f'/api/contacts/{c["id"]}/enrich')
    assert response.status_code == 409
    current = client.get(f'/api/contacts/{c["id"]}').json()
    assert current["email"] == "" and current["name"] == "Jane Doe"
    assert len(current["sources"]) == 1


@pytest.mark.parametrize(
    "person,status",
    [
        (None, "not_found"),
        (
            {
                "linkedin_url": "https://www.linkedin.com/in/jane-doe",
                "email": "email_not_unlocked@domain.com",
                "email_status": "verified",
            },
            "unavailable",
        ),
    ],
)
def test_no_match_and_no_email_have_distinct_states(client, upstream, person, status):
    _, reply = upstream
    reply["person"] = person
    c = discover(client)["items"][0]
    response = client.post(f'/api/contacts/{c["id"]}/enrich')
    assert response.status_code == 200
    assert response.json()["contact"]["email"] == ""
    assert response.json()["contact"]["email_status"] == status


def test_apollo_permission_failure_preserves_google_result(client, upstream):
    _, reply = upstream
    reply["status"] = 403
    reply["error_code"] = "API_INACCESSIBLE"
    c = discover(client)["items"][0]
    response = client.post(f'/api/contacts/{c["id"]}/enrich')
    assert response.status_code == 502 and "403" in response.json()["detail"]
    assert "API_INACCESSIBLE" in response.json()["detail"]
    current = client.get(f'/api/contacts/{c["id"]}').json()
    assert current["provider"] == "serpapi" and not current["email"]
    assert len(current["sources"]) == 1


def test_missing_serpapi_key_does_not_search_apollo(client, upstream, monkeypatch):
    calls, _ = upstream
    monkeypatch.setattr(settings, "serpapi_api_key", "")
    response = client.post("/api/finance/search", json={})
    assert response.status_code == 503 and not calls


def test_pagination_uses_google_offset(client, upstream):
    calls, _ = upstream
    response = client.post("/api/finance/search", json={"page": 2, "per_page": 10})
    assert response.status_code == 200
    assert calls[0].url.params["start"] == "10"


def test_discovery_does_not_skip_additional_public_sources(client, upstream):
    calls, _ = upstream
    c = discover(client)["items"][0]
    response = client.post(f'/api/contacts/{c["id"]}/public-sources')
    assert response.status_code == 200
    assert len(calls) == 2
    assert {s["kind"] for s in response.json()["sources"]} == {
        "discovery",
        "unverified_lead",
    }
    client.post(f'/api/contacts/{c["id"]}/public-sources')
    assert len(calls) == 2


@pytest.mark.parametrize(
    "url",
    [
        "https://linkedin.com.evil.test/in/jane",
        "javascript:alert(1)",
        "https://linkedin.com/company/firm",
        "https://linkedin.com/in/jane/posts",
        "https://linkedin.com/in/a%2Fb",
    ],
)
def test_reject_non_person_urls(url):
    assert linkedin_profile(url) == ""
