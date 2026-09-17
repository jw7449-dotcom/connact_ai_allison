import pytest

from app.config import settings
from app.providers.serpapi import SerpAPIPeople
from app.services.people_jobs import process_job, stop_people_worker


def organic(count):
    return [
        {
            "title": f"Person {n} - Analyst",
            "link": f"https://www.linkedin.com/in/person-{n}",
        }
        for n in range(count)
    ]


@pytest.mark.parametrize(
    ("metadata", "count", "has_more"),
    [
        ({"serpapi_pagination": {"next": "https://serpapi.com/search?start=10"}}, 8, True),
        ({"serpapi_pagination": {"next_link": "https://serpapi.com/search?start=10"}}, 8, True),
        ({"pagination": {"next": "https://google.com/search?start=10"}}, 8, True),
        ({"serpapi_pagination": {"other_pages": {"2": "next-url"}}}, 8, True),
        ({}, 10, True),
        ({}, 8, False),
        ({}, 0, False),
        ({"serpapi_pagination": {"current": 1}}, 10, False),
        ({"serpapi_pagination": {"other_pages": {"1": "previous-url"}}}, 10, False),
    ],
)
def test_provider_pagination_respects_links_and_missing_metadata(
    monkeypatch, metadata, count, has_more
):
    monkeypatch.setattr(
        "app.providers.serpapi.request_json",
        lambda *args, **kwargs: {
            "organic_results": organic(count),
            # A large Google estimate must not override an explicit final page.
            "search_information": {"total_results": 100_000},
            **metadata,
        },
    )
    result = SerpAPIPeople().search({"page": 1, "per_page": 10})
    assert result["has_more"] is has_more
    assert result["total_is_estimate"] is True


def test_duplicate_profiles_do_not_hide_a_following_raw_search_page(monkeypatch):
    rows = organic(9)
    rows.append(rows[0])
    monkeypatch.setattr(
        "app.providers.serpapi.request_json",
        lambda *args, **kwargs: {"organic_results": rows},
    )
    result = SerpAPIPeople().search({"page": 1, "per_page": 10})
    assert len(result["people"]) == 9
    assert result["has_more"] is True


def test_async_pages_are_distinct_and_returning_reuses_saved_contact(client, monkeypatch):
    stop_people_worker()
    monkeypatch.setattr(settings, "people_mode", "mock")

    def search(page):
        response = client.post(
            "/api/finance/search/jobs", json={"page": page, "per_page": 10}
        )
        assert response.status_code == 202, response.text
        job_id = response.json()["job"]["id"]
        process_job(job_id)
        job = client.get("/api/people/jobs/" + job_id).json()
        assert job["status"] == "succeeded", job
        return job, response.json()["cached"]

    first, _ = search(1)
    first_ids = {person["id"] for person in first["result"]["items"]}
    assert len(first_ids) == 10
    assert first["result"]["has_more"] is True
    saved_id = next(iter(first_ids))
    assert client.post(f"/api/contacts/{saved_id}/save").status_code == 200

    second, _ = search(2)
    second_ids = {person["id"] for person in second["result"]["items"]}
    assert len(second_ids) == 6
    assert not first_ids.intersection(second_ids)
    assert second["result"]["page"] == 2
    assert second["result"]["has_more"] is False

    restored, cached = search(1)
    assert cached is True
    assert restored["id"] == first["id"]
    assert next(c for c in restored["result"]["items"] if c["id"] == saved_id)["saved"]
