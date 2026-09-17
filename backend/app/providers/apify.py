"""Public professional profiles via a bounded, asynchronous Apify Actor run.

Contract verified against harvestapi/linkedin-profile-scraper build 0.0.135.
Email search is deliberately independent from public profile retrieval.
"""

import re
import httpx
from fastapi import HTTPException
from ..config import settings
from .base import request_json, budget
from .linkedin import linkedin_profile

BASE = "https://api.apify.com/v2"


def text(value, limit=8000):
    return value.strip()[:limit] if isinstance(value, str) else ""


def date(value):
    if isinstance(value, dict):
        return text(value.get("text"), 80) or str(value.get("year") or "")
    return text(value, 80)


def normalize_profile(item, expected_url):
    """Store only documented professional fields; never infer facts from filters."""
    if not isinstance(item, dict) or item.get("error"):
        raise HTTPException(502, "Apify could not retrieve this public profile.")
    actual = linkedin_profile(item.get("linkedinUrl"))
    if not actual or actual != linkedin_profile(expected_url):
        raise HTTPException(
            409,
            "Apify returned a different or unidentified LinkedIn profile. No information was attached.",
        )
    experience = [
        {
            "title": text(x.get("position"), 500),
            "company": text(x.get("companyName"), 500),
            "location": text(x.get("location"), 500),
            "start_date": date(x.get("startDate")),
            "end_date": date(x.get("endDate")),
            "description": text(x.get("description"), 8000),
        }
        for x in (item.get("experience") or [])[:50]
        if isinstance(x, dict)
    ]
    education = [
        {
            "school": text(x.get("schoolName"), 500),
            "degree": text(x.get("degree"), 500),
            "field_of_study": text(x.get("fieldOfStudy"), 500),
            "start_date": date(x.get("startDate")),
            "end_date": date(x.get("endDate")),
        }
        for x in (item.get("education") or [])[:30]
        if isinstance(x, dict)
    ]
    skills = [
        text(x.get("name") if isinstance(x, dict) else x, 200)
        for x in (item.get("skills") or [])[:100]
    ]
    location = item.get("location") or {}
    location = location.get("linkedinText") if isinstance(location, dict) else location
    name = text(item.get("fullName"), 200) or " ".join(
        filter(
            None, [text(item.get("firstName"), 100), text(item.get("lastName"), 100)]
        )
    )
    positions = [x for x in (item.get("currentPosition") or []) if isinstance(x, dict)]
    current = next(
        (x for x in experience if x["end_date"].lower() in ("present", "current")), {}
    )
    fields = {
        "name": name,
        "title": current.get("title") or text(item.get("headline"), 250),
        "company": (
            text(positions[0].get("companyName"), 250)
            if positions
            else current.get("company", "")
        ),
        "location": text(location, 250),
        "school": education[0]["school"][:250] if education else "",
    }
    professional = {
        "summary": text(item.get("about"), 16000),
        "headline": text(item.get("headline"), 1000),
        "experience": experience,
        "education": education,
        "skills": list(dict.fromkeys(filter(None, skills))),
        "source_provider": "apify",
        "source_url": actual,
    }
    if not name or not any((professional["headline"], experience, education)):
        raise HTTPException(
            502,
            "Apify returned an incomplete profile without usable professional details.",
        )
    return {
        "fields": {
            k: v[:250] if k != "name" else v[:200] for k, v in fields.items() if v
        },
        "professional": professional,
    }


class ApifyProfileProvider:
    def request(self, method, path, **kwargs):
        return request_json(
            "Apify",
            method,
            BASE + path,
            settings.apify_api_key,
            headers={"Authorization": "Bearer " + settings.apify_api_key},
            **kwargs,
        )

    def start(self, profile_url, find_email=False):
        profile = linkedin_profile(profile_url)
        if not profile:
            raise HTTPException(422, "A valid public LinkedIn person URL is required.")
        actor = settings.apify_profile_actor.replace("/", "~")
        data = self.request(
            "POST",
            f"/acts/{actor}/runs",
            params={
                "timeout": 180,
                "memory": 256,
                "maxTotalChargeUsd": settings.apify_max_charge_usd,
            },
            json={
                "queries": [profile],
                "profileScraperMode": (
                    "Profile details + email search ($10 per 1k)"
                    if find_email
                    else "Profile details no email ($4 per 1k)"
                ),
            },
        )
        run = data.get("data") or {}
        if not run.get("id"):
            raise HTTPException(
                502,
                "Apify did not return a run ID. Check the provider console before retrying.",
            )
        return {"run_id": run["id"], "dataset_id": run.get("defaultDatasetId", "")}

    def poll(self, run_id):
        run = self.request("GET", "/actor-runs/" + run_id).get("data") or {}
        return {
            "status": run.get("status"),
            "dataset_id": run.get("defaultDatasetId", ""),
        }

    def result(self, dataset_id, profile_url, find_email=False):
        if not settings.apify_api_key:
            raise HTTPException(503, "Apify API key is missing.")
        budget("Apify")
        try:
            with httpx.Client(timeout=35) as client:
                response = client.get(
                    BASE + "/datasets/" + dataset_id + "/items",
                    headers={"Authorization": "Bearer " + settings.apify_api_key},
                    params={"clean": "true", "limit": 2},
                )
            if response.status_code >= 400:
                raise HTTPException(
                    502,
                    f"Apify dataset returned HTTP {response.status_code}. Retry reading this run.",
                )
            items = response.json()
        except (httpx.HTTPError, ValueError):
            raise HTTPException(
                502,
                "Could not read the completed Apify dataset. Retry reading this run.",
            )
        if not isinstance(items, list) or len(items) != 1:
            raise HTTPException(502, "Apify did not return exactly one public profile.")
        result = normalize_profile(items[0], profile_url)
        if find_email:
            result["email"] = normalize_email(items[0])
        return result


def normalize_email(item):
    # Profile 'verified' concerns LinkedIn identity, not email verification.
    emails = item.get("emails") or []
    if not isinstance(emails, list):
        raise HTTPException(502, "Apify returned an unsupported email result format.")
    for entry in emails:
        value = (
            entry
            if isinstance(entry, str)
            else entry.get("email", "") if isinstance(entry, dict) else ""
        )
        if not isinstance(value, str) or not re.fullmatch(
            r"[^\s@]+@[^\s@]+\.[^\s@]+", value
        ):
            continue
        detail = entry if isinstance(entry, dict) else {}
        kind = str(detail.get("type") or detail.get("emailType") or "unknown").lower()
        if kind in ("personal", "private") or value.rsplit("@", 1)[1].lower() in {
            "gmail.com",
            "yahoo.com",
            "hotmail.com",
            "outlook.com",
            "icloud.com",
            "aol.com",
            "qq.com",
            "163.com",
        }:
            continue
        reported = (
            detail.get("status")
            or detail.get("verificationStatus")
            or detail.get("emailStatus")
            or "not_provided"
        )
        if detail.get("deliverable") is False or str(reported).lower() in (
            "invalid",
            "undeliverable",
            "disposable",
        ):
            continue
        checks = {
            key: detail[key]
            for key in (
                "deliverable",
                "catchAllDomain",
                "validEmailServer",
                "free",
                "qualityScore",
            )
            if key in detail and isinstance(detail[key], (bool, int, float))
        }
        # Keep the raw provider label separately; no assumed validation from marketing claims.
        return {
            "email": value[:250],
            "email_status": "unverified",
            "provider_status": str(reported)[:100],
            "email_type": kind,
            "provider_checks": checks,
        }
    return {
        "email": "",
        "email_status": "unavailable",
        "provider_status": "not_provided",
        "email_type": "unknown",
    }
