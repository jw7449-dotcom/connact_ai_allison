from fastapi import APIRouter, Depends, HTTPException
from ..db import get_repo
from ..models import (
    Contact,
    ContactDomainProfile,
    SourceEvidence,
    Draft,
    now,
    PeopleJob,
)
from ..schemas import ContactInput, ContactJobInput
from ..services.contacts import row, contact_json, lock_contact
from ..services.people_jobs import enqueue, serialize, fresh, apply_email
from ..providers import people_enrichment, public_search
from ..config import settings

router = APIRouter()


@router.get("/contacts")
def contacts(repo=Depends(get_repo)):
    return [contact_json(repo, c) for c in repo.all(Contact, Contact.saved == True)]


@router.get("/contacts/{id}")
def detail(id: str, repo=Depends(get_repo)):
    result = contact_json(repo, repo.get(Contact, id))
    result["drafts"] = [row(d) for d in repo.all(Draft, Draft.contact_id == id)]
    return result


def set_fields(repo, c, body):
    data = body.model_dump()
    sector = data.pop("sector")
    email_changed = c.email != data["email"]
    if any(
        getattr(c, key) != data[key]
        for key in (
            "name",
            "title",
            "company",
            "location",
            "school",
            "profile_url",
            "email",
        )
    ):
        for job in repo.all(PeopleJob, PeopleJob.contact_id == c.id):
            job.result = {**job.result, "cache_invalidated": True}
            if job.status in ("queued", "waiting"):
                job.status = "failed"
                job.error = "Contact was edited. Start a new task using the updated contact details."
                job.retryable = False
    if c.profile_url != data["profile_url"] or c.name != data["name"]:
        for profile in repo.all(
            ContactDomainProfile,
            ContactDomainProfile.contact_id == c.id,
            ContactDomainProfile.domain == "professional",
        ):
            repo.session.delete(profile)
        for evidence in repo.all(
            SourceEvidence,
            SourceEvidence.contact_id == c.id,
            SourceEvidence.provider == "apify",
        ):
            repo.session.delete(evidence)
    if any(
        getattr(c, k) != data[k] for k in ("name", "company", "profile_url", "email")
    ):
        for evidence in repo.all(
            SourceEvidence,
            SourceEvidence.contact_id == c.id,
            SourceEvidence.kind == "enrichment",
        ):
            repo.session.delete(evidence)
    for k, v in data.items():
        setattr(c, k, v)
    if email_changed:
        c.email_status = "unverified" if c.email else "not_requested"
    profiles = repo.all(
        ContactDomainProfile,
        ContactDomainProfile.contact_id == c.id,
        ContactDomainProfile.domain == "finance",
    )
    if profiles:
        profiles[0].data = {"sector": sector}
    else:
        repo.add(
            ContactDomainProfile,
            contact_id=c.id,
            domain="finance",
            data={"sector": sector},
        )
    repo.add(
        SourceEvidence,
        contact_id=c.id,
        provider="manual",
        url=c.profile_url,
        title="User-entered contact details",
        snippet=f"{c.name} | {c.title} | {c.company} | {c.location}",
        kind="manual",
    )


@router.post("/contacts")
def create(body: ContactInput, repo=Depends(get_repo)):
    c = repo.add(Contact, name=body.name, saved=True, provider="manual")
    set_fields(repo, c, body)
    return contact_json(repo, c)


@router.put("/contacts/{id}")
def update(id: str, body: ContactInput, repo=Depends(get_repo)):
    c = lock_contact(repo, id)
    set_fields(repo, c, body)
    for draft in repo.all(Draft, Draft.contact_id == id):
        draft.status = "draft"
        draft.revision += 1
    return contact_json(repo, c)


@router.post("/contacts/{id}/save")
def save(id: str, repo=Depends(get_repo)):
    c = repo.get(Contact, id)
    already = c.saved
    c.saved = True
    return {"contact": contact_json(repo, c), "already_saved": already}


@router.post("/contacts/{id}/enrich")
def enrich(id: str, repo=Depends(get_repo)):
    c = repo.get(Contact, id)
    allowed = (
        {"mock"} if settings.people_mode == "mock" else {"serpapi", "apollo", "manual"}
    )
    if c.provider not in allowed:
        raise HTTPException(
            409,
            "This contact belongs to a different provider mode. Search again in the active mode, or edit it manually.",
        )
    evidence = repo.all(
        SourceEvidence,
        SourceEvidence.contact_id == id,
        SourceEvidence.kind == "enrichment",
    )
    evidence = [
        e
        for e in evidence
        if e.provider == ("mock" if settings.people_mode == "mock" else "apollo")
        and fresh(e.retrieved_at, settings.people_cache_hours)
    ]
    if evidence:
        return {"contact": contact_json(repo, c), "cached": True}
    version = c.updated_at
    data = people_enrichment().enrich(row(c))
    c = lock_contact(repo, id)
    if c.updated_at != version:
        raise HTTPException(
            409,
            "Contact changed while enrichment was running. No result was attached; retry using the updated details.",
        )
    apply_email(repo, c, data)
    return {"contact": contact_json(repo, c), "cached": False}


@router.post("/contacts/{id}/public-sources")
def sources(id: str, repo=Depends(get_repo)):
    c = repo.get(Contact, id)
    existing = repo.all(
        SourceEvidence,
        SourceEvidence.contact_id == id,
        SourceEvidence.kind == "unverified_lead",
        SourceEvidence.provider
        == ("mock" if settings.public_search_mode == "mock" else "serpapi"),
    )
    if not existing:
        version = c.updated_at
        evidence = public_search().search(row(c))[:3]
        c = lock_contact(repo, id)
        if c.updated_at != version:
            raise HTTPException(
                409,
                "Contact changed while sources were being retrieved. No sources were attached; retry using the updated details.",
            )
        for e in evidence:
            repo.add(SourceEvidence, contact_id=id, **e)
    return contact_json(repo, c)


@router.post("/contacts/{id}/jobs", status_code=202)
def start_contact_job(id: str, body: ContactJobInput, repo=Depends(get_repo)):
    contact = repo.get(Contact, id)
    job, cached = enqueue(repo, body.kind, {}, contact, body.force)
    return {"job": serialize(repo, job), "cached": cached}


@router.get("/people/jobs/{id}")
def people_job(id: str, repo=Depends(get_repo)):
    return serialize(repo, repo.get(PeopleJob, id))


@router.post("/people/jobs/{id}/retry", status_code=202)
def retry_people_job(id: str, repo=Depends(get_repo)):
    job = repo.get(PeopleJob, id)
    if job.status != "failed" or not job.retryable:
        raise HTTPException(
            409, "This task cannot be retried. Check its status and provider run first."
        )
    job.status = "queued"
    job.error = ""
    return serialize(repo, job)
