from typing import Protocol
from collections import defaultdict, deque
from threading import Lock
from time import monotonic
import httpx
from fastapi import HTTPException
from ..config import settings


class PeopleSearchProvider(Protocol):
    def search(self, filters: dict) -> dict: ...


class PeopleEnrichmentProvider(Protocol):
    def enrich(self, contact: dict) -> dict: ...


class PublicSearchProvider(Protocol):
    def search(self, contact: dict) -> list[dict]: ...


class AIProvider(Protocol):
    def complete(self, task: str, data: dict) -> dict: ...


_calls = defaultdict(deque)
_lock = Lock()


class LocalProviderRateLimit(HTTPException):
    """No network request has occurred; background jobs can safely defer."""


def budget(provider: str):
    # Per-process limit across requests and background jobs. Every upstream request is counted.
    with _lock:
        calls, clock = _calls[provider], monotonic()
        while calls and calls[0] < clock - 60:
            calls.popleft()
        if len(calls) >= settings.provider_calls_per_minute:
            raise LocalProviderRateLimit(
                429, f"{provider}: local call limit reached. Retry in a minute."
            )
        calls.append(clock)


def request_json(provider, method, url, key, **kwargs):
    if not key:
        raise HTTPException(
            503,
            f"{provider} is in Live mode but its API key is missing. Configure it on the server.",
        )
    budget(provider)
    try:
        with httpx.Client(timeout=35) as client:
            res = client.request(method, url, **kwargs)
        if res.status_code >= 400:
            code = 429 if res.status_code == 429 else 502
            if provider == "Apollo" and res.status_code == 403:
                try:
                    reason = res.json()
                except ValueError:
                    reason = {}
                if (
                    isinstance(reason, dict)
                    and reason.get("error_code") == "API_INACCESSIBLE"
                ):
                    raise HTTPException(
                        502,
                        "Apollo HTTP 403 / API_INACCESSIBLE: your plan does not include people/match. "
                        "当前 Apollo 套餐未开放人物匹配与邮箱补充 API；请在 Apollo 开通该接口权限后重试。Google 搜索结果已保留。",
                    )
            raise HTTPException(
                code,
                f"{provider} returned HTTP {res.status_code}. Check API access, quota and filters. No mock fallback was used.",
            )
        data = res.json()
        if not isinstance(data, dict) or data.get("error"):
            raise ValueError("Invalid provider result")
        return data
    except (httpx.HTTPError, ValueError):
        raise HTTPException(
            502,
            f"{provider} request failed or returned invalid data. No mock fallback was used.",
        )
