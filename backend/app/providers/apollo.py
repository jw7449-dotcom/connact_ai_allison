from .base import request_json
from ..config import settings
from .linkedin import linkedin_profile
from fastapi import HTTPException
import re

BASE = "https://api.apollo.io/api/v1"


def safe_url(value):
    return (
        value
        if isinstance(value, str) and value.startswith(("http://", "https://"))
        else ""
    )


class ApolloProvider:
    def post(self, endpoint, data):
        return request_json(
            "Apollo",
            "POST",
            BASE + endpoint,
            settings.apollo_api_key,
            headers={
                "x-api-key": settings.apollo_api_key,
                "Content-Type": "application/json",
            },
            params=data,
        )

    def enrich(self, contact):
        profile = linkedin_profile(contact.get("profile_url"))
        payload = {"reveal_personal_emails": False, "reveal_phone_number": False}
        if contact.get("provider") != "apollo" and profile:
            if not profile:
                raise HTTPException(
                    422, "A valid LinkedIn person URL is required for Apollo matching."
                )
            payload["linkedin_url"] = profile
        elif contact.get("provider_id"):
            payload["id"] = contact["provider_id"]
        else:
            raise HTTPException(422, "No Apollo ID or LinkedIn person URL available.")
        result = self.post(
            "/people/match",
            payload,
        )
        p = result.get("person")
        if not isinstance(p, dict):
            return {"email": "", "email_status": "not_found"}
        if contact.get("provider") != "apollo" and profile:
            matched = linkedin_profile(p.get("linkedin_url"))
            confidence = result.get("match_confidence", p.get("match_confidence"))
            if matched != profile or confidence in ("none", "low"):
                raise HTTPException(
                    409,
                    "Apollo could not confirm the same LinkedIn profile. Contact and email were not changed.",
                )
        email = p.get("email") or ""
        if (
            not isinstance(email, str)
            or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email)
            or email.endswith("@domain.com")
            or "email_not_unlocked" in email
        ):
            email = ""
        data = {
            "email": email,
            "email_status": (
                (p.get("email_status") or "unverified") if email else "unavailable"
            ),
        }
        if p.get("name"):
            data["name"] = p["name"][:200]
        if p.get("linkedin_url"):
            data["profile_url"] = linkedin_profile(p["linkedin_url"]) or safe_url(
                p["linkedin_url"]
            )
        if p.get("title"):
            data["title"] = p["title"][:250]
        if (p.get("organization") or {}).get("name"):
            data["company"] = p["organization"]["name"][:250]
        location = ", ".join(p[x] for x in ("city", "state", "country") if p.get(x))
        if location:
            data["location"] = location[:250]
        return data
