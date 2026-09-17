"""Durable jobs for the single-process workspace server.

Apify run IDs are committed before polling. Restart resumes submitted runs;
ambiguous paid submissions are surfaced rather than submitted twice.
"""

import hashlib
import json
import logging
from datetime import timedelta, timezone
from threading import Event, Thread, Lock
from sqlalchemy import select, update, or_
from fastapi import HTTPException
from ..config import settings
from ..db import Session, WorkspaceRepository
from ..models import (
    PeopleJob,
    Contact,
    ContactDomainProfile,
    SourceEvidence,
    Draft,
    now,
)
from ..providers import people_search, people_enrichment
from ..providers.apify import ApifyProfileProvider
from ..providers.base import LocalProviderRateLimit
from ..providers.linkedin import linkedin_profile
from .contacts import row, contact_json, upsert_search, lock_contact

ACTIVE = ("queued", "running", "waiting")
_stop = Event()
_thread = None
_enqueue_lock = Lock()
_claim_lock = Lock()
# At most ten automatic profile runs are in flight on the single API process.
PROFILE_CONCURRENCY = 10
_log = logging.getLogger(__name__)


def fresh(date, hours):
    return date is not None and date.replace(tzinfo=timezone.utc) > now() - timedelta(
        hours=hours
    )


def search_profile_states(repo, job, contacts=None):
    """Read current readiness; a saved search is never proof of an intact profile."""
    states = {}
    for contact_id in job.result.get("contact_ids", []):
        stored = job.result.get("profiles", {}).get(contact_id)
        if stored is None:
            contact = (contacts or {}).get(contact_id) or contact_json(
                repo, repo.get(Contact, contact_id)
            )
            professional = contact["professional"]
            if contact["provider"] == "mock":
                states[contact_id] = {"status": "skipped", "error": ""}
            elif professional.get("retrieved_at") and linkedin_profile(
                professional.get("source_url")
            ) == linkedin_profile(contact["profile_url"]):
                states[contact_id] = {
                    "status": "succeeded",
                    "error": "",
                    "cached": True,
                }
            else:
                states[contact_id] = {
                    "status": "failed",
                    "invalidated": True,
                    "error": "This saved search predates automatic profile preparation. Search again to prepare details.",
                }
            continue
        state = dict(stored)
        state.pop("invalidated", None)
        if state.get("job_id"):
            child = repo.get(PeopleJob, state["job_id"])
            repo.session.refresh(child)
            state.update(status=child.status, error=child.error)
            if child.result.get("cache_invalidated"):
                state.update(
                    status="failed",
                    invalidated=True,
                    error="Contact was edited. Search again to prepare its current profile.",
                )
            elif child.status == "succeeded":
                contact = (contacts or {}).get(contact_id) or contact_json(
                    repo, repo.get(Contact, contact_id)
                )
                professional = contact["professional"]
                if not professional.get("retrieved_at") or linkedin_profile(
                    professional.get("source_url")
                ) != linkedin_profile(contact["profile_url"]):
                    state.update(
                        status="failed",
                        invalidated=True,
                        error="The saved professional profile is no longer available for this contact. Search again to prepare details.",
                    )
        states[contact_id] = state
    return states


def profile_progress(states):
    return {
        "total": len(states),
        "ready": sum(s["status"] == "succeeded" for s in states.values()),
        "failed": sum(s["status"] == "failed" for s in states.values()),
        "skipped": sum(s["status"] == "skipped" for s in states.values()),
        "pending": sum(s["status"] in ACTIVE for s in states.values()),
    }


def serialize(repo, job, include_result=True):
    data = row(job)
    data.pop("fingerprint", None)
    # Public response contains run ID for support, never provider credentials.
    if include_result and job.status == "succeeded":
        if job.kind == "search":
            contacts = {
                id: contact_json(repo, repo.get(Contact, id))
                for id in job.result.get("contact_ids", [])
            }
            states = search_profile_states(repo, job, contacts)
            data["result"] = {
                **job.result,
                "profiles": states,
                "profile_progress": profile_progress(states),
                "items": [
                    {
                        **contacts[id],
                        "profile_prefetch": states.get(id),
                    }
                    for id in job.result.get("contact_ids", [])
                ],
            }
        elif job.contact_id:
            data["result"] = {
                **job.result,
                "contact": contact_json(repo, repo.get(Contact, job.contact_id)),
            }
    return data


def enqueue(repo, kind, payload, contact=None, force=False, reuse_failed=False):
    if kind not in ("search", "profile", "email", "email_apify"):
        raise HTTPException(422, "Unknown people job type.")
    if contact:
        if kind in ("profile", "email_apify") and (
            settings.people_mode == "mock" or contact.provider == "mock"
        ):
            raise HTTPException(
                409, "Public profile retrieval needs a live LinkedIn contact."
            )
        if kind in ("profile", "email_apify") and not settings.apify_api_key:
            raise HTTPException(503, "Apify is not configured on the server.")
        if kind in ("profile", "email_apify") and not linkedin_profile(
            contact.profile_url
        ):
            raise HTTPException(
                422, "Add a public LinkedIn person URL before retrieving the profile."
            )
        allowed = (
            {"mock"}
            if settings.people_mode == "mock"
            else {"serpapi", "apollo", "manual"}
        )
        if kind == "email" and contact.provider not in allowed:
            raise HTTPException(409, "This contact belongs to another provider mode.")
        payload = {**payload, "contact": row(contact)}
        # Contact dates are not part of the upstream request snapshot.
        payload["contact"].pop("created_at", None)
        payload["contact"].pop("updated_at", None)
    payload = {**payload, "mode": settings.people_mode}
    identity = (
        ({**payload, "pipeline_version": 3} if kind == "search" else payload)
        if not contact
        else {
            "mode": settings.people_mode,
            "contact_id": contact.id,
            "provider": contact.provider,
            "profile_url": linkedin_profile(contact.profile_url) or contact.profile_url,
            "provider_id": contact.provider_id,
        }
    )
    fingerprint = hashlib.sha256(
        json.dumps({"kind": kind, "input": identity}, sort_keys=True).encode()
    ).hexdigest()
    with _enqueue_lock:
        jobs = sorted(
            repo.all(PeopleJob, PeopleJob.fingerprint == fingerprint),
            key=lambda j: j.created_at,
        )
        active = next((j for j in reversed(jobs) if j.status in ACTIVE), None)
        if active:
            return active, True
        cached = next(
            (
                j
                for j in reversed(jobs)
                if j.status == "succeeded"
                and not j.result.get("cache_invalidated")
                and fresh(
                    j.updated_at, 1 if kind == "search" else settings.people_cache_hours
                )
                and (
                    kind != "search"
                    or not any(
                        s.get("invalidated")
                        for s in search_profile_states(repo, j).values()
                    )
                )
                and (
                    kind != "profile"
                    or any(
                        p.data.get("retrieved_at")
                        and linkedin_profile(p.data.get("source_url"))
                        == linkedin_profile(contact.profile_url)
                        for p in repo.all(
                            ContactDomainProfile,
                            ContactDomainProfile.contact_id == contact.id,
                            ContactDomainProfile.domain == "professional",
                        )
                    )
                )
            ),
            None,
        )
        if cached and not force:
            return cached, True
        # Page preparation must not resubmit failed paid work on every search.
        # An uncertain submission stays blocked until explicitly reviewed.
        if reuse_failed and not force:
            failed = next(
                (
                    j
                    for j in reversed(jobs)
                    if j.status == "failed"
                    and not j.result.get("cache_invalidated")
                    and (
                        not j.retryable
                        or fresh(j.updated_at, settings.people_cache_hours)
                    )
                ),
                None,
            )
            if failed:
                return failed, True
        job = repo.add(
            PeopleJob,
            kind=kind,
            contact_id=contact.id if contact else None,
            input=payload,
            fingerprint=fingerprint,
        )
        # Commit before worker receives it, including any pending contact changes.
        repo.session.commit()
        return job, False


def prepare_search_profiles(repo, job):
    """Resume page preparation without repeating discovery or profile submissions."""
    states = dict(job.result.get("profiles", {}))
    for contact_id in job.result["contact_ids"]:
        if contact_id in states:
            continue
        contact = repo.get(Contact, contact_id)
        if settings.people_mode == "mock" or contact.provider == "mock":
            states[contact_id] = {"status": "skipped", "error": ""}
        else:
            try:
                child, cached = enqueue(
                    repo, "profile", {"automatic": True}, contact, reuse_failed=True
                )
                states[contact_id] = {
                    "job_id": child.id,
                    "status": child.status,
                    "cached": cached,
                    "error": child.error,
                }
            except HTTPException as exc:
                states[contact_id] = {"status": "failed", "error": str(exc.detail)}
        # A restart between enqueue and this commit finds the same fingerprint.
        job.result = {**job.result, "profiles": states}
        repo.session.commit()
    states = search_profile_states(repo, job)
    progress = profile_progress(states)
    job.result = {
        **job.result,
        "profiles": states,
        "profile_progress": progress,
        "phase": "profiles" if progress["pending"] else "complete",
    }
    job.status = "waiting" if progress["pending"] else "succeeded"
    job.next_poll_at = now() + timedelta(seconds=2) if progress["pending"] else None


def apply_email(repo, contact, data, provider=None):
    for key, value in data.items():
        if key in (
            "name",
            "title",
            "company",
            "location",
            "school",
            "profile_url",
            "email",
            "email_status",
        ):
            if (
                key in ("email", "email_status")
                and not data.get("email")
                and contact.email
            ):
                continue
            setattr(contact, key, value)
    for draft in repo.all(Draft, Draft.contact_id == contact.id):
        draft.status = "draft"
        draft.revision += 1
    repo.add(
        SourceEvidence,
        contact_id=contact.id,
        provider=provider or ("mock" if settings.people_mode == "mock" else "apollo"),
        url=contact.profile_url,
        title="On-demand contact enrichment",
        snippet=f"{contact.name} | {contact.title} | {contact.company} | Email status: {contact.email_status}; provider status: {data.get('provider_status',contact.email_status)}; address type: {data.get('email_type','not_provided')}"
        + (
            "; provider checks: "
            + ", ".join(
                f"{key}={value}" for key, value in data["provider_checks"].items()
            )
            if data.get("provider_checks")
            else ""
        ),
        kind="enrichment",
    )


def apply_profile(repo, contact, data):
    for key, value in data["fields"].items():
        setattr(contact, key, value)
    professional = dict(data["professional"])
    evidence = repo.add(
        SourceEvidence,
        contact_id=contact.id,
        provider="apify",
        url=professional["source_url"],
        title="Public professional profile via Apify",
        snippet=" | ".join(
            filter(
                None,
                [
                    professional["summary"][:1200],
                    "Work: "
                    + "; ".join(
                        " · ".join(
                            filter(
                                None,
                                [
                                    x["title"],
                                    x["company"],
                                    x["start_date"],
                                    x["end_date"],
                                ],
                            )
                        )
                        for x in professional["experience"][:15]
                    ),
                    "Education: "
                    + "; ".join(
                        " · ".join(
                            filter(
                                None, [x["school"], x["degree"], x["field_of_study"]]
                            )
                        )
                        for x in professional["education"][:10]
                    ),
                ],
            )
        ),
        kind="profile",
    )
    professional.update(source_id=evidence.id, retrieved_at=now().isoformat())
    rows = repo.all(
        ContactDomainProfile,
        ContactDomainProfile.contact_id == contact.id,
        ContactDomainProfile.domain == "professional",
    )
    if rows:
        rows[0].data = professional
    else:
        repo.add(
            ContactDomainProfile,
            contact_id=contact.id,
            domain="professional",
            data=professional,
        )
    for draft in repo.all(Draft, Draft.contact_id == contact.id):
        draft.status = "draft"
        draft.revision += 1


def verify_identity(contact, before):
    # Provider normalization can update names without changing the canonical person.
    if contact.profile_url != before.get("profile_url") or (
        not contact.profile_url and contact.name != before.get("name")
    ):
        raise HTTPException(
            409,
            "Contact identity changed during this task. No result was attached; start again for the current contact.",
        )


def process_job(job_id):
    with Session() as session:
        job = session.get(PeopleJob, job_id)
        if not job or job.status not in ("queued", "waiting"):
            return
        old_status = job.status
        with _claim_lock:
            if (
                job.kind == "profile"
                and job.input.get("automatic")
                and not job.upstream.get("run_id")
            ):
                in_flight = session.scalars(
                    select(PeopleJob).where(
                        PeopleJob.kind.in_(("profile", "email_apify")),
                        PeopleJob.status.in_(("running", "waiting")),
                        PeopleJob.id != job_id,
                    )
                ).all()
                if (
                    sum(
                        j.status == "running" or bool(j.upstream.get("run_id"))
                        for j in in_flight
                    )
                    >= PROFILE_CONCURRENCY
                ):
                    return
            claimed = session.execute(
                update(PeopleJob)
                .where(PeopleJob.id == job_id, PeopleJob.status == old_status)
                .values(status="running")
            )
            if not claimed.rowcount:
                session.rollback()
                return
            job.attempts += 1
            session.commit()
        repo = WorkspaceRepository(session, job.workspace_id)
        stage = "read"
        try:
            if job.input.get("mode") != settings.people_mode:
                raise HTTPException(
                    409,
                    "Provider mode changed after this task was created. Start a new task in the current mode.",
                )
            contact = repo.get(Contact, job.contact_id) if job.contact_id else None
            if job.result.get("cache_invalidated"):
                raise HTTPException(
                    409,
                    "Contact was edited. Start a new task using the updated contact details.",
                )
            if contact:
                verify_identity(contact, job.input["contact"])
            if job.kind == "search":
                if "contact_ids" not in job.result:
                    filters = {k: v for k, v in job.input.items() if k != "mode"}
                    result = people_search().search(filters)
                    found = [
                        upsert_search(repo, item)
                        for item in result["people"][: filters["per_page"]]
                    ]
                    job.result = {
                        "contact_ids": list(dict.fromkeys(c.id for c in found)),
                        "total": result["total"],
                        "page": filters["page"],
                        "per_page": filters["per_page"],
                        "mode": settings.people_mode,
                        "has_more": result.get(
                            "has_more",
                            filters["page"] * filters["per_page"] < result["total"],
                        ),
                        "total_is_estimate": result.get("total_is_estimate", False),
                        "phase": "profiles",
                    }
                    session.commit()
                prepare_search_profiles(repo, job)
            elif job.kind == "email":
                data = people_enrichment().enrich(job.input["contact"])
                contact = lock_contact(repo, job.contact_id)
                session.refresh(job)
                if job.result.get("cache_invalidated"):
                    raise HTTPException(
                        409,
                        "Contact was edited. Start a new task using the updated contact details.",
                    )
                verify_identity(contact, job.input["contact"])
                apply_email(repo, contact, data)
                job.result = {"email_status": contact.email_status}
                job.status = "succeeded"
            else:
                provider = ApifyProfileProvider()
                if not job.upstream.get("run_id"):
                    stage = "submission"
                    upstream = provider.start(
                        job.input["contact"]["profile_url"],
                        find_email=job.kind == "email_apify",
                    )
                    job.upstream = upstream
                    job.status = "waiting"
                    job.next_poll_at = now() + timedelta(seconds=5)
                    session.commit()
                    return
                status = provider.poll(job.upstream["run_id"])
                if status["status"] in ("READY", "RUNNING", "TIMING-OUT", "ABORTING"):
                    job.status = "waiting"
                    job.next_poll_at = now() + timedelta(seconds=8)
                elif status["status"] == "SUCCEEDED":
                    data = provider.result(
                        status["dataset_id"] or job.upstream["dataset_id"],
                        job.input["contact"]["profile_url"],
                        find_email=job.kind == "email_apify",
                    )
                    contact = lock_contact(repo, job.contact_id)
                    session.refresh(job)
                    if job.result.get("cache_invalidated"):
                        raise HTTPException(
                            409,
                            "Contact was edited. Start a new task using the updated contact details.",
                        )
                    verify_identity(contact, job.input["contact"])
                    if job.kind == "email_apify":
                        apply_email(repo, contact, data["email"], provider="apify")
                    else:
                        apply_profile(repo, contact, data)
                    job.result = {
                        "fields_found": list(data["fields"]),
                        "experience_count": len(data["professional"]["experience"]),
                        "education_count": len(data["professional"]["education"]),
                    }
                    if job.kind == "email_apify":
                        job.result.update(data["email"])
                    job.status = "succeeded"
                else:
                    job.retryable = False
                    raise HTTPException(
                        502,
                        f"Apify run ended with status {status['status'] or 'unknown'}. Start a fresh profile task to retry.",
                    )
            job.error = ""
            session.commit()
        except LocalProviderRateLimit as exc:
            session.rollback()
            job = session.get(PeopleJob, job_id)
            job.status = "waiting"
            job.next_poll_at = now() + timedelta(seconds=61)
            job.error = str(exc.detail)
            session.commit()
        except Exception as exc:
            # Roll back partial enrichment while retaining the durable job record.
            session.rollback()
            job = session.get(PeopleJob, job_id)
            job.status = "failed"
            if (
                job.kind in ("profile", "email_apify")
                and job.upstream.get("run_id")
                and isinstance(exc, HTTPException)
                and exc.status_code in (429, 502)
            ):
                failures = job.upstream.get("read_failures", 0) + 1
                job.upstream = {**job.upstream, "read_failures": failures}
                if failures <= 3 and "ended with status" not in str(exc.detail):
                    job.status = "waiting"
                    job.next_poll_at = now() + timedelta(seconds=20 * failures)
            job.error = (
                exc.detail
                if isinstance(exc, HTTPException)
                else "The people task failed. Please retry or check server logs."
            )
            if isinstance(exc, HTTPException) and "ended with status" in str(
                exc.detail
            ):
                job.retryable = False
            if job.result.get("cache_invalidated"):
                job.retryable = False
            if stage == "submission":
                job.retryable = False
                job.error += " The launch outcome may be uncertain; check Apify runs before starting another paid request."
            session.commit()


def recover_jobs():
    with Session() as session:
        for job in session.scalars(
            select(PeopleJob).where(PeopleJob.status == "running")
        ):
            if (job.kind == "search" and "contact_ids" in job.result) or (
                job.kind in ("profile", "email_apify") and job.upstream.get("run_id")
            ):
                job.status = "waiting"
                job.next_poll_at = now()
            else:
                job.status = "failed"
                job.error = "Server restarted during this request. Its outcome is uncertain; check the provider before retrying."
                job.retryable = job.kind not in ("profile", "email_apify")
        session.commit()


def tick():
    with Session() as session:
        ids = session.scalars(
            select(PeopleJob.id)
            .where(
                or_(
                    PeopleJob.status == "queued",
                    (PeopleJob.status == "waiting") & (PeopleJob.next_poll_at <= now()),
                )
            )
            .order_by(PeopleJob.created_at)
            .limit(5)
        ).all()
    for id in ids:
        if _stop.is_set():
            break
        process_job(id)


def start_people_worker():
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    recover_jobs()

    def loop():
        while not _stop.wait(1):
            try:
                tick()
            except Exception:
                _log.error("People worker could not process jobs; will retry.")

    _thread = Thread(target=loop, name="people-jobs", daemon=True)
    _thread.start()


def stop_people_worker():
    global _thread
    _stop.set()
    if _thread:
        _thread.join(timeout=40)
        if not _thread.is_alive():
            _thread = None
