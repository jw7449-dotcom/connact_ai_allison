from .base import request_json
from .apollo import safe_url
from ..config import settings
from .linkedin import linkedin_profile
import hashlib
import re
from fastapi import HTTPException


def has_next_page(result, page, per_page, organic_count):
    # SerpAPI has emitted both `next` and `next_link`; Google pagination and
    # numbered links can also identify the next page. Do not infer accessible
    # pages from Google's approximate total_results count.
    pagination = [
        value
        for key in ("serpapi_pagination", "pagination")
        if isinstance(value := result.get(key), dict)
    ]
    for value in pagination:
        if value.get("next") or value.get("next_link"):
            return True
        other_pages = value.get("other_pages")
        if isinstance(other_pages, dict) and other_pages.get(str(page + 1)):
            return True
    if pagination:
        return False
    # Missing pagination metadata is not proof of the last page. A full raw
    # page allows another explicit request; a short/empty page ends discovery.
    # Count raw results here because URL deduplication can shrink the UI page.
    return organic_count >= per_page


class SerpAPIPeople:
    def search(self, filters):
        # Filters are search terms, never asserted as facts about a result.
        terms = [
            filters.get(k, "").strip()
            for k in ("title", "company", "location", "sector", "keywords")
        ]
        query = "site:linkedin.com/in/ " + " ".join(x for x in terms if x)
        start = (filters["page"] - 1) * filters["per_page"]
        result = request_json(
            "SerpAPI",
            "GET",
            "https://serpapi.com/search.json",
            settings.serpapi_api_key,
            params={
                "api_key": settings.serpapi_api_key,
                "engine": "google",
                "q": query.strip(),
                "start": start,
                "num": filters["per_page"],
            },
        )
        organic = result.get("organic_results", [])
        if not isinstance(organic, list):
            raise HTTPException(502, "SerpAPI returned invalid search results.")
        people, seen = [], set()
        for hit in organic[: filters["per_page"]]:
            if not isinstance(hit, dict):
                continue
            url = linkedin_profile(hit.get("link"))
            if not url or url in seen:
                continue
            headline = re.sub(
                r"\s*[|–—-]\s*LinkedIn\s*$", "", hit.get("title") or "", flags=re.I
            )
            parts = re.split(r"\s+[–—-]\s+", headline, maxsplit=1)
            name = parts[0].strip()
            if not name:
                continue
            seen.add(url)
            people.append(
                {
                    "provider": "serpapi",
                    "provider_id": hashlib.sha256(url.encode()).hexdigest(),
                    "name": name[:200],
                    "title": parts[1][:250] if len(parts) > 1 else "",
                    "company": "",
                    "location": "",
                    "school": "",
                    "sector": "",
                    "profile_url": url,
                    "email": "",
                    "email_status": "not_requested",
                    "search_evidence": {
                        "title": (hit.get("title") or "Google profile result")[:500],
                        "snippet": hit.get("snippet") or "",
                    },
                }
            )
        estimated = (result.get("search_information") or {}).get("total_results", 0)
        total = int(estimated) if str(estimated).isdigit() else start + len(organic)
        return {
            "people": people,
            "total": total,
            "total_is_estimate": True,
            "has_more": has_next_page(
                result, filters["page"], filters["per_page"], len(organic)
            ),
        }


class SerpAPIProvider:
    def search(self, contact):
        result = request_json(
            "SerpAPI",
            "GET",
            "https://serpapi.com/search.json",
            settings.serpapi_api_key,
            params={
                "api_key": settings.serpapi_api_key,
                "engine": "google",
                "q": f'"{contact["name"]}" "{contact["company"]}" {contact["title"]}',
                "num": 3,
            },
        )
        return [
            {
                "provider": "serpapi",
                "url": safe_url(r.get("link")),
                "title": (r.get("title") or "")[:500],
                "snippet": r.get("snippet") or "",
                "kind": "unverified_lead",
            }
            for r in result.get("organic_results", [])[:3]
        ]
