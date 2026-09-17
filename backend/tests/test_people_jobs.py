import json
from datetime import timedelta
import httpx
import pytest
from fastapi import HTTPException
from app.config import settings
from app.db import Session, WorkspaceRepository
from app.models import Contact, PeopleJob, Workspace, now
from app.providers.apify import normalize_profile
from app.providers.base import _calls
from app.services.people_jobs import process_job, recover_jobs, stop_people_worker

URL = "https://www.linkedin.com/in/jane-doe"


def profile():
    return {
        "linkedinUrl": URL,
        "firstName": "Jane",
        "lastName": "Doe",
        "headline": "Analyst",
        "about": "Works on financial analysis",
        "location": {"linkedinText": "London"},
        "currentPosition": [{"companyName": "Actual Firm"}],
        "experience": [
            {
                "position": "Analyst",
                "companyName": "Actual Firm",
                "startDate": {"text": "2024"},
                "endDate": {"text": "Present"},
            }
        ],
        "education": [
            {
                "schoolName": "Actual University",
                "degree": "BA",
                "fieldOfStudy": "Economics",
                "startDate": {"year": 2020},
            }
        ],
        "skills": [{"name": "Analysis"}],
        "emails": ["ignored@example.com"],
    }


@pytest.fixture
def live(monkeypatch):
    stop_people_worker()
    _calls.clear()
    monkeypatch.setattr(settings, "people_mode", "live")
    monkeypatch.setattr(settings, "apify_api_key", "test-only")
    monkeypatch.setattr(settings, "serpapi_api_key", "test-only")
    monkeypatch.setattr(settings, "apollo_api_key", "test-only")
    calls = []
    item = profile()
    run = {"status": "SUCCEEDED", "defaultDatasetId": "dataset-1"}
    original = httpx.Client

    def handle(req):
        calls.append(req)
        if req.url.host == "serpapi.com":
            return httpx.Response(
                200,
                json={
                    "organic_results": [
                        {
                            "title": "Jane Doe - Analyst",
                            "link": URL,
                            "snippet": "A public search result",
                        }
                    ],
                    "search_information": {"total_results": 1},
                },
            )
        if req.method == "POST" and req.url.host == "api.apify.com":
            assert json.loads(req.content)["queries"] == [URL]
            assert json.loads(req.content)["profileScraperMode"] in (
                "Profile details no email ($4 per 1k)",
                "Profile details + email search ($10 per 1k)",
            )
            assert req.url.params["maxTotalChargeUsd"] == "0.05"
            assert "token" not in req.url.params
            return httpx.Response(
                201, json={"data": {"id": "run-1", "defaultDatasetId": "dataset-1"}}
            )
        if "/actor-runs/" in req.url.path:
            return httpx.Response(200, json={"data": run})
        if "/datasets/" in req.url.path:
            return httpx.Response(200, json=[item])
        return httpx.Response(403, json={"error_code": "API_INACCESSIBLE"})

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kw: original(transport=httpx.MockTransport(handle), **kw),
    )
    return calls, item, run


def new_contact(client):
    return client.post(
        "/api/contacts", json={"name": "Jane Doe", "profile_url": URL}
    ).json()


def start(client, c, kind="profile"):
    r = client.post("/api/contacts/" + c["id"] + "/jobs", json={"kind": kind})
    assert r.status_code == 202, r.text
    return r.json()["job"]


def test_profile_job_survives_restart_and_no_email_guess(client, live):
    calls, _, _ = live
    c = new_contact(client)
    job = start(client, c)
    process_job(job["id"])
    waiting = client.get("/api/people/jobs/" + job["id"]).json()
    assert waiting["status"] == "waiting" and waiting["upstream"]["run_id"] == "run-1"
    assert start(client, c)["id"] == job["id"]
    with Session() as db:
        db.get(PeopleJob, job["id"]).status = "running"
        db.commit()
    recover_jobs()
    process_job(job["id"])
    done = client.get("/api/people/jobs/" + job["id"]).json()
    assert done["status"] == "succeeded", done
    c = done["result"]["contact"]
    assert c["email"] == "" and "email" in c["missing_fields"]
    assert c["company"] == "Actual Firm"
    assert c["professional"]["education"][0]["degree"] == "BA"
    assert c["professional"]["experience"][0]["start_date"] == "2024"
    assert c["professional"]["source_id"] in [x["id"] for x in c["sources"]]
    assert (
        start(client, c)["id"] == job["id"]
    )  # enriched fields do not invalidate the cache
    assert len([r for r in calls if r.method == "POST"]) == 1


def test_apollo_denied_does_not_erase_profile(client, live):
    c = new_contact(client)
    job = start(client, c)
    process_job(job["id"])
    process_job(job["id"])
    job = start(client, c, "email")
    process_job(job["id"])
    failed = client.get("/api/people/jobs/" + job["id"]).json()
    assert failed["status"] == "failed" and "API_INACCESSIBLE" in failed["error"]
    detail = client.get("/api/contacts/" + c["id"]).json()
    assert detail["professional"]["education"] and not detail["email"]


def test_async_search_history_and_workspace_scope(client, live):
    r = client.post("/api/finance/search/jobs", json={"company": "Filter Firm"}).json()[
        "job"
    ]
    process_job(r["id"])
    preparing = client.get("/api/people/jobs/" + r["id"]).json()
    assert preparing["status"] == "waiting"
    assert preparing["result"]["profile_progress"]["pending"] == 1
    assert "items" not in preparing["result"]
    child_id = next(iter(preparing["result"]["profiles"].values()))["job_id"]
    process_job(child_id)
    process_job(child_id)
    process_job(r["id"])
    done = client.get("/api/people/jobs/" + r["id"]).json()
    assert done["status"] == "succeeded"
    contact = done["result"]["items"][0]
    assert contact["company"] == "Actual Firm"
    assert contact["professional"]["education"][0]["degree"] == "BA"
    assert contact["profile_prefetch"]["status"] == "succeeded"
    assert contact["email"] == "" and contact["email_status"] == "not_requested"
    assert all(r.url.host != "api.apollo.io" for r in live[0])
    for request in live[0]:
        if request.method == "POST":
            assert (
                json.loads(request.content)["profileScraperMode"]
                == "Profile details no email ($4 per 1k)"
            )
    assert client.get("/api/finance/search/jobs").json()[0]["id"] == r["id"]
    assert client.post(
        "/api/finance/search/jobs", json={"company": "Filter Firm"}
    ).json()["cached"]
    with Session() as db:
        db.add(Workspace(id="other", name="Other"))
        db.commit()
        other = WorkspaceRepository(db, "other")
        with pytest.raises(HTTPException) as exc:
            other.get(PeopleJob, r["id"])
        assert exc.value.status_code == 404


def test_profile_identity_conflict_keeps_original(client, live):
    _, item, _ = live
    c = new_contact(client)
    job = start(client, c)
    process_job(job["id"])
    item["linkedinUrl"] = "https://www.linkedin.com/in/somebody-else"
    process_job(job["id"])
    done = client.get("/api/people/jobs/" + job["id"]).json()
    assert done["status"] == "failed"
    assert client.get("/api/contacts/" + c["id"]).json()["professional"] == {}


def search_page(client, **filters):
    job = client.post("/api/finance/search/jobs", json=filters).json()["job"]
    process_job(job["id"])
    return client.get("/api/people/jobs/" + job["id"]).json()


def test_page_reuses_profile_cache_across_searches_and_gets_never_submit(client, live):
    first = search_page(client, company="First filter")
    child_id = next(iter(first["result"]["profiles"].values()))["job_id"]
    process_job(child_id)
    process_job(child_id)
    process_job(first["id"])
    second = search_page(client, company="Different filter")
    assert second["status"] == "succeeded"
    c = second["result"]["items"][0]
    assert c["profile_prefetch"]["cached"] and c["professional"]["experience"]
    requests_before = len(live[0])
    for _ in range(3):
        assert client.get("/api/contacts/" + c["id"]).status_code == 200
        assert client.get("/api/people/jobs/" + second["id"]).status_code == 200
    assert len(live[0]) == requests_before
    assert len([r for r in live[0] if r.method == "POST"]) == 1


@pytest.mark.parametrize("has_profile", [False, True])
def test_old_search_history_reports_current_profile_or_search_again_without_fetching(
    client, live, has_profile
):
    page = search_page(client, company="Old saved filter")
    child = next(iter(page["result"]["profiles"].values()))["job_id"]
    if has_profile:
        process_job(child)
        process_job(child)
    with Session() as db:
        job = db.get(PeopleJob, page["id"])
        job.status = "succeeded"
        job.result = {
            k: v
            for k, v in job.result.items()
            if k not in ("profiles", "phase", "profile_progress")
        }
        db.commit()
    before = len(live[0])
    result = client.get("/api/people/jobs/" + page["id"]).json()
    state = result["result"]["items"][0]["profile_prefetch"]
    assert state["status"] == ("succeeded" if has_profile else "failed")
    if not has_profile:
        assert "Search again" in state["error"]
    assert len(live[0]) == before


@pytest.mark.parametrize("remove_snapshot", [False, True])
def test_search_cache_rejects_edited_or_missing_professional_snapshot(
    client, live, remove_snapshot
):
    from app.models import ContactDomainProfile

    first = search_page(client, company="Same filter")
    contact_id = first["result"]["contact_ids"][0]
    child_id = first["result"]["profiles"][contact_id]["job_id"]
    process_job(child_id)
    process_job(child_id)
    process_job(first["id"])
    if remove_snapshot:
        with Session() as db:
            repo = WorkspaceRepository(db, settings.workspace_id)
            for profile in repo.all(
                ContactDomainProfile,
                ContactDomainProfile.contact_id == contact_id,
                ContactDomainProfile.domain == "professional",
            ):
                db.delete(profile)
            db.commit()
    else:
        edited = client.put(
            "/api/contacts/" + contact_id,
            json={
                "name": "Updated Person",
                "company": "User edited company",
                "profile_url": "https://www.linkedin.com/in/updated-person",
            },
        )
        assert edited.status_code == 200
    requests_before = len(live[0])
    old = client.get("/api/people/jobs/" + first["id"]).json()
    assert old["result"]["items"][0]["profile_prefetch"]["status"] == "failed"
    assert old["result"]["profile_progress"]["ready"] == 0
    assert len(live[0]) == requests_before
    new = client.post(
        "/api/finance/search/jobs", json={"company": "Same filter"}
    ).json()
    assert not new["cached"] and new["job"]["id"] != first["id"]
    process_job(new["job"]["id"])
    preparing = client.get("/api/people/jobs/" + new["job"]["id"]).json()
    assert preparing["status"] == "waiting"
    assert preparing["result"]["profiles"][contact_id]["job_id"] != child_id
    if not remove_snapshot:
        current = client.get("/api/contacts/" + contact_id).json()
        assert current["company"] == "User edited company"
        assert current["name"] == "Updated Person"


def test_profile_failure_finishes_page_and_is_not_resubmitted_by_next_search(
    client, live
):
    live[2]["status"] = "FAILED"
    first = search_page(client, company="First filter")
    child_id = next(iter(first["result"]["profiles"].values()))["job_id"]
    process_job(child_id)
    process_job(child_id)
    process_job(first["id"])
    done = client.get("/api/people/jobs/" + first["id"]).json()
    assert done["status"] == "succeeded"
    assert done["result"]["profile_progress"] == {
        "total": 1,
        "ready": 0,
        "pending": 0,
        "failed": 1,
        "skipped": 0,
    }
    c = done["result"]["items"][0]
    assert c["professional"] == {} and "FAILED" in c["profile_prefetch"]["error"]
    second = search_page(client, company="Different filter")
    assert second["status"] == "succeeded"
    assert second["result"]["items"][0]["profile_prefetch"]["job_id"] == child_id
    assert len([r for r in live[0] if r.method == "POST"]) == 1


def test_missing_profile_configuration_keeps_discovery_results(
    client, live, monkeypatch
):
    monkeypatch.setattr(settings, "apify_api_key", "")
    result = search_page(client, company="First filter")
    assert result["status"] == "succeeded"
    c = result["result"]["items"][0]
    assert c["name"] == "Jane Doe" and c["profile_prefetch"]["status"] == "failed"
    assert "not configured" in c["profile_prefetch"]["error"]
    assert all(r.url.host == "serpapi.com" for r in live[0])


def test_restart_during_page_preparation_reuses_discovery_and_profile_jobs(
    client, live
):
    page = search_page(client, company="Restart filter")
    child_id = next(iter(page["result"]["profiles"].values()))["job_id"]
    process_job(child_id)
    with Session() as db:
        parent = db.get(PeopleJob, page["id"])
        parent.status = "running"
        # Simulate a restart after enqueue's commit but before the parent stored its child ID.
        parent.result = {**parent.result, "profiles": {}}
        db.get(PeopleJob, child_id).status = "running"
        db.commit()
    recover_jobs()
    process_job(page["id"])
    process_job(child_id)
    process_job(page["id"])
    done = client.get("/api/people/jobs/" + page["id"]).json()
    assert (
        done["status"] == "succeeded"
        and done["result"]["profile_progress"]["ready"] == 1
    )
    assert len([r for r in live[0] if r.url.host == "serpapi.com"]) == 1
    assert len([r for r in live[0] if r.method == "POST"]) == 1


def test_automatic_profiles_limit_inflight_runs_and_retrieve_only_current_page(
    client, live, monkeypatch
):
    import app.services.people_jobs as service
    from app.providers.apify import ApifyProfileProvider

    contacts = [new_contact(client)]
    for n in range(1, 12):
        contacts.append(
            client.post(
                "/api/contacts",
                json={
                    "name": f"Person {n}",
                    "profile_url": f"https://www.linkedin.com/in/person-{n}",
                },
            ).json()
        )
    starts = []

    def launch(self, url, find_email=False):
        assert not find_email
        starts.append(url)
        return {"run_id": "run-" + str(len(starts)), "dataset_id": "dataset"}

    monkeypatch.setattr(ApifyProfileProvider, "start", launch)
    with Session() as db:
        repo = WorkspaceRepository(db, settings.workspace_id)
        jobs = [
            service.enqueue(
                repo, "profile", {"automatic": True}, repo.get(Contact, c["id"])
            )[0].id
            for c in contacts
        ]
    for id in jobs:
        process_job(id)
    assert len(starts) == 10
    assert client.get("/api/people/jobs/" + jobs[10]).json()["status"] == "queued"
    with Session() as db:
        db.get(PeopleJob, jobs[0]).status = "succeeded"
        db.commit()
    process_job(jobs[10])
    process_job(jobs[11])
    assert len(starts) == 11
    assert client.get("/api/people/jobs/" + jobs[11]).json()["status"] == "queued"
    # Search page two creates no requests for subsequent pages.
    monkeypatch.setattr(settings, "apify_api_key", "")
    page = search_page(client, company="Page filter", page=2, per_page=1)
    assert page["result"]["page"] == 2 and len(page["result"]["items"]) == 1
    searches = [r for r in live[0] if r.url.host == "serpapi.com"]
    assert len(searches) == 1 and searches[0].url.params["start"] == "1"


def test_local_provider_limit_defers_submission_and_reads_without_false_uncertainty(
    client, live, monkeypatch
):
    monkeypatch.setattr(settings, "provider_calls_per_minute", 1)
    first = start(client, new_contact(client))
    process_job(first["id"])
    other = client.post(
        "/api/contacts",
        json={"name": "Other", "profile_url": "https://www.linkedin.com/in/other"},
    ).json()
    second = start(client, other)
    process_job(second["id"])
    deferred = client.get("/api/people/jobs/" + second["id"]).json()
    assert deferred["status"] == "waiting" and deferred["retryable"]
    assert deferred["upstream"] == {} and "uncertain" not in deferred["error"]
    assert len([r for r in live[0] if r.method == "POST"]) == 1
    # A run already submitted waits for local read capacity without consuming
    # transient provider-failure retries or forgetting the paid run ID.
    for _ in range(5):
        process_job(first["id"])
    waiting = client.get("/api/people/jobs/" + first["id"]).json()
    assert waiting["status"] == "waiting" and waiting["upstream"]["run_id"] == "run-1"
    assert not waiting["upstream"].get("read_failures")
    _calls.clear()
    monkeypatch.setattr(settings, "provider_calls_per_minute", 20)
    process_job(first["id"])
    assert client.get("/api/people/jobs/" + first["id"]).json()["status"] == "succeeded"


def test_manual_identity_edit_invalidates_running_profile(client, live):
    c = new_contact(client)
    job = start(client, c)
    process_job(job["id"])
    client.put(
        "/api/contacts/" + c["id"],
        json={
            "name": "Somebody Else",
            "profile_url": "https://www.linkedin.com/in/somebody-else",
        },
    )
    process_job(job["id"])
    assert client.get("/api/people/jobs/" + job["id"]).json()["status"] == "failed"
    assert client.get("/api/contacts/" + c["id"]).json()["professional"] == {}


def test_ambiguous_launch_is_not_auto_retried(client, live, monkeypatch):
    from app.providers.apify import ApifyProfileProvider

    def fail(*a, **kw):
        raise HTTPException(502, "Transport failed")

    monkeypatch.setattr(ApifyProfileProvider, "start", fail)
    c = new_contact(client)
    job = start(client, c)
    process_job(job["id"])
    failed = client.get("/api/people/jobs/" + job["id"]).json()
    assert failed["status"] == "failed" and not failed["retryable"]
    assert client.post("/api/people/jobs/" + job["id"] + "/retry").status_code == 409


def test_normalizer_never_copies_email_or_profile_verification():
    data = normalize_profile({**profile(), "verified": True}, URL)
    assert "email" not in data["fields"] and "email_status" not in data["fields"]
    assert "verified" not in data["professional"]


def test_independent_apify_email_provider_and_status(client, live):
    calls, item, _ = live
    item["emails"] = [{"email": "jane@firm.example", "status": "valid", "type": "work"}]
    c = new_contact(client)
    job = start(client, c, "email_apify")
    process_job(job["id"])
    process_job(job["id"])
    done = client.get("/api/people/jobs/" + job["id"]).json()
    assert done["status"] == "succeeded", done
    assert done["result"]["provider_status"] == "valid"
    c = done["result"]["contact"]
    assert c["email"] == "jane@firm.example" and c["email_status"] == "unverified"
    assert (
        c["professional"] == {}
    )  # this independent email task does not modify profile context
    assert c["sources"][-1]["provider"] == "apify"
    assert all(r.url.host != "api.apollo.io" for r in calls)
    assert (
        json.loads(calls[0].content)["profileScraperMode"]
        == "Profile details + email search ($10 per 1k)"
    )


def test_email_parser_does_not_treat_profile_badge_as_mail_validation():
    from app.providers.apify import normalize_email

    assert (
        normalize_email({"verified": True, "emails": ["jane@company.example"]})[
            "email_status"
        ]
        == "unverified"
    )
    assert (
        normalize_email(
            {
                "emails": [
                    {"email": "jane@gmail.com", "status": "valid", "type": "personal"}
                ]
            }
        )["email"]
        == ""
    )


def test_manual_edit_invalidates_cache_but_provider_enrichment_does_not(client, live):
    c = new_contact(client)
    job = start(client, c)
    process_job(job["id"])
    process_job(job["id"])
    current = client.get("/api/contacts/" + c["id"]).json()
    assert start(client, current)["id"] == job["id"]
    client.put(
        "/api/contacts/" + c["id"],
        json={"name": "Jane Doe", "company": "Updated by user", "profile_url": URL},
    )
    assert start(client, c)["id"] != job["id"]


def test_actual_apify_email_shape_retains_checks_and_rejects_invalid():
    from app.providers.apify import normalize_email

    email = {
        "email": "jane@firm.example",
        "deliverable": True,
        "catchAllDomain": False,
        "validEmailServer": True,
        "free": False,
        "status": "valid",
        "qualityScore": 80,
    }
    value = normalize_email({"emails": [email]})
    assert value["provider_status"] == "valid" and value["email_status"] == "unverified"
    assert (
        value["provider_checks"]["deliverable"] is True
        and value["provider_checks"]["qualityScore"] == 80
    )
    assert normalize_email({"emails": [{**email, "deliverable": False}]})["email"] == ""


def test_invite_people_jobs_and_sources_are_workspace_isolated(
    client, live, monkeypatch
):
    import secrets
    from app.auth_models import Invitation
    from app.models import SourceEvidence
    from app.routers.auth import digest, _attempts
    from app.services.people_jobs import stop_people_worker

    stop_people_worker()
    monkeypatch.setattr(settings, "auth_mode", "invite")
    _attempts.clear()

    def join(email):
        token = secrets.token_urlsafe(32)
        with Session() as db:
            db.add(
                Invitation(
                    email=email,
                    token_hash=digest(token),
                    expires_at=now() + timedelta(days=1),
                )
            )
            db.commit()
        response = client.post(
            "/api/auth/join",
            json={
                "email": email,
                "password": "test-password-12345",
                "invitation": token,
            },
        )
        assert response.status_code == 200, response.text
        return response.json()["workspace_id"]

    a = join("people-a@example.test")
    search_a = client.post(
        "/api/finance/search/jobs", json={"company": "Same Firm"}
    ).json()["job"]
    process_job(search_a["id"])
    contact_id_a = client.get("/api/people/jobs/" + search_a["id"]).json()["result"][
        "contact_ids"
    ][0]
    contact_a = client.get("/api/contacts/" + contact_id_a).json()
    profile_a = start(client, contact_a)
    client.post("/api/auth/logout")
    b = join("people-b@example.test")
    assert a != b
    assert client.get("/api/finance/search/jobs").json() == []
    for path in [
        "/api/contacts/" + contact_a["id"],
        "/api/people/jobs/" + search_a["id"],
        "/api/people/jobs/" + profile_a["id"],
    ]:
        assert client.get(path).status_code == 404
    assert (
        client.post(
            "/api/contacts/" + contact_a["id"] + "/jobs", json={"kind": "profile"}
        ).status_code
        == 404
    )
    assert (
        client.post("/api/people/jobs/" + profile_a["id"] + "/retry").status_code == 404
    )
    # The background worker must preserve the job owner while B is logged in.
    process_job(profile_a["id"])
    process_job(profile_a["id"])
    search_b = client.post(
        "/api/finance/search/jobs", json={"company": "Same Firm"}
    ).json()["job"]
    process_job(search_b["id"])
    contact_id_b = client.get("/api/people/jobs/" + search_b["id"]).json()["result"][
        "contact_ids"
    ][0]
    contact_b = client.get("/api/contacts/" + contact_id_b).json()
    assert contact_b["id"] != contact_a["id"]
    assert contact_b["professional"] == {} and len(contact_b["jobs"]) == 1
    assert contact_b["jobs"][0]["status"] == "queued"
    assert {x["id"] for x in contact_b["sources"]}.isdisjoint(
        {x["id"] for x in contact_a["sources"]}
    )
    with Session() as db:
        wrong = WorkspaceRepository(db, b).add(
            SourceEvidence,
            contact_id=contact_a["id"],
            provider="manual",
            title="Foreign evidence",
            snippet="must not leak",
            kind="manual",
        )
        wrong_id = wrong.id
        db.commit()
        assert db.get(PeopleJob, profile_a["id"]).workspace_id == a
    client.post("/api/auth/logout")
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "people-a@example.test", "password": "test-password-12345"},
        ).status_code
        == 200
    )
    own = client.get("/api/contacts/" + contact_a["id"]).json()
    assert own["professional"]["education"] and wrong_id not in {
        x["id"] for x in own["sources"]
    }
    assert client.get("/api/people/jobs/" + search_b["id"]).status_code == 404
    assert [x["id"] for x in client.get("/api/finance/search/jobs").json()] == [
        search_a["id"]
    ]


def test_edit_during_upstream_result_never_overwrites_user_fields_or_sources(
    client, live, monkeypatch
):
    from app.providers.apify import ApifyProfileProvider
    from app.services.people_jobs import stop_people_worker

    stop_people_worker()
    c = new_contact(client)
    job = start(client, c)
    process_job(job["id"])

    def finish_after_edit(*args, **kwargs):
        edited = client.put(
            "/api/contacts/" + c["id"],
            json={
                "name": "Jane Doe",
                "company": "User edited company",
                "profile_url": URL,
            },
        )
        assert edited.status_code == 200, edited.text
        return normalize_profile(profile(), URL)

    monkeypatch.setattr(ApifyProfileProvider, "result", finish_after_edit)
    process_job(job["id"])
    result = client.get("/api/people/jobs/" + job["id"]).json()
    assert result["status"] == "failed" and not result["retryable"]
    current = client.get("/api/contacts/" + c["id"]).json()
    assert current["company"] == "User edited company" and current["professional"] == {}
    assert all(source["provider"] != "apify" for source in current["sources"])


def test_competing_workers_submit_one_upstream_run(client, live, monkeypatch):
    from threading import Event, Thread
    from app.providers.apify import ApifyProfileProvider
    from app.services.people_jobs import stop_people_worker

    stop_people_worker()
    c = new_contact(client)
    job = start(client, c)
    entered, release = Event(), Event()
    submissions = []

    def hold(*args, **kwargs):
        submissions.append(True)
        entered.set()
        assert release.wait(3)
        return {"run_id": "one-run", "dataset_id": "one-dataset"}

    monkeypatch.setattr(ApifyProfileProvider, "start", hold)
    worker = Thread(target=process_job, args=(job["id"],))
    worker.start()
    try:
        assert entered.wait(2)
        process_job(job["id"])
    finally:
        release.set()
        worker.join(3)
    assert not worker.is_alive() and len(submissions) == 1
    assert (
        client.get("/api/people/jobs/" + job["id"]).json()["upstream"]["run_id"]
        == "one-run"
    )


def test_failed_retry_reuses_run_id_without_second_submission(
    client, live, monkeypatch
):
    from app.providers.apify import ApifyProfileProvider
    from app.services.people_jobs import stop_people_worker

    stop_people_worker()
    calls, _, _ = live
    c = new_contact(client)
    job = start(client, c)
    process_job(job["id"])
    with Session() as db:
        j = db.get(PeopleJob, job["id"])
        j.status = "failed"
        j.error = "Temporary dataset outage"
        db.commit()
    assert client.post("/api/people/jobs/" + job["id"] + "/retry").status_code == 202
    process_job(job["id"])
    assert client.get("/api/people/jobs/" + job["id"]).json()["status"] == "succeeded"
    assert len([r for r in calls if r.method == "POST"]) == 1


def test_contact_and_sources_roll_back_together_when_job_commit_fails(
    client, live, monkeypatch
):
    import app.services.people_jobs as service

    service.stop_people_worker()
    c = new_contact(client)
    job = start(client, c)
    process_job(job["id"])
    original = service.apply_profile

    def fail_after_profile(repo, contact, data):
        original(repo, contact, data)
        repo.session.flush()
        raise RuntimeError("Simulated storage failure")

    monkeypatch.setattr(service, "apply_profile", fail_after_profile)
    process_job(job["id"])
    failed = client.get("/api/people/jobs/" + job["id"]).json()
    assert failed["status"] == "failed" and failed["upstream"]["run_id"] == "run-1"
    current = client.get("/api/contacts/" + c["id"]).json()
    assert current["company"] == "" and current["professional"] == {}
    assert all(source["provider"] != "apify" for source in current["sources"])


def test_legacy_sync_email_rejects_result_after_manual_change(
    client, live, monkeypatch
):
    from app.providers.apollo import ApolloProvider
    from app.services.people_jobs import stop_people_worker

    stop_people_worker()
    c = new_contact(client)

    def provider_result(*a, **kw):
        changed = client.put(
            "/api/contacts/" + c["id"],
            json={
                "name": "Jane Doe",
                "company": "Keep user company",
                "profile_url": URL,
            },
        )
        assert changed.status_code == 200
        return {"email": "stale@firm.example", "email_status": "unverified"}

    monkeypatch.setattr(ApolloProvider, "enrich", provider_result)
    response = client.post("/api/contacts/" + c["id"] + "/enrich")
    assert response.status_code == 409, response.text
    current = client.get("/api/contacts/" + c["id"]).json()
    assert current["email"] == "" and current["company"] == "Keep user company"
    assert all(source["provider"] != "apollo" for source in current["sources"])
