"""Server-owned model routes. Public catalogs never contain endpoints or secrets."""

import os
from urllib.parse import urlsplit
from dataclasses import dataclass, field
from fastapi import HTTPException
from ..config import AIProviderConfig, settings

PRESETS = [
    AIProviderConfig(
        id="bailian",
        label="Bailian MaaS · 百炼多厂商",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key_env="DASHSCOPE_API_KEY",
        models=[
            "qwen3.8-flash",
            "deepseek-v4-flash",
            "kimi-k3",
            "glm-5.2",
            "MiniMax-M2.5",
        ],
    ),
]


@dataclass(frozen=True)
class ModelRoute:
    id: str
    model: str
    provider: str
    provider_label: str
    base_url: str
    api_key: str = field(repr=False)
    protocol: str = "compatible"
    token_parameter: str = "max_tokens"
    json_mode: bool = True
    thinking_mode: str = "auto"

    @property
    def configured(self):
        return bool(self.api_key)


def model_routes():
    # Keep the existing unqualified IDs working for saved drafts and deployments.
    legacy = list(
        dict.fromkeys(v.strip() for v in settings.ai_models.split(",") if v.strip())
    ) or [settings.ai_model]
    legacy_label = {
        "bailian": "Bailian MaaS · 百炼多厂商",
        "dashscope": "Bailian MaaS · 百炼多厂商",
        "compatible": "Configured endpoint",
    }.get(settings.ai_provider, settings.ai_provider)
    routes = {
        m: ModelRoute(
            m,
            m,
            settings.ai_provider,
            legacy_label,
            settings.ai_base_url,
            settings.ai_api_key,
            token_parameter="max_completion_tokens",
        )
        for m in legacy
    }
    providers = {p.id: p for p in PRESETS}
    providers.update({p.id: p for p in settings.ai_providers})
    for provider in providers.values():
        key = getattr(settings, provider.api_key_env.lower(), None)
        if key is None:
            key = os.environ.get(provider.api_key_env, "")
        # Reuse the existing key only for the exact same official Bailian endpoint.
        # A provider label alone must never authorize sending it to another host.
        if (
            not key
            and provider.id in {"bailian", "qwen"}
            and provider.api_key_env == "DASHSCOPE_API_KEY"
            and provider.base_url.rstrip("/") == settings.ai_base_url.rstrip("/")
            and is_bailian_endpoint(provider.base_url)
        ):
            key = settings.ai_api_key
        for model in provider.models:
            ident = provider.id + "/" + model
            routes[ident] = ModelRoute(
                ident,
                model,
                provider.id,
                provider.label,
                provider.base_url,
                key,
                provider.protocol,
                provider.token_parameter,
                provider.json_mode,
                provider.thinking_mode,
            )
    return routes


def is_bailian_endpoint(base_url):
    url = urlsplit(base_url)
    return (
        url.scheme == "https"
        and url.hostname
        in {
            "dashscope.aliyuncs.com",
            "dashscope-intl.aliyuncs.com",
            "dashscope-us.aliyuncs.com",
        }
        and url.path.rstrip("/") == "/compatible-mode/v1"
        and not url.username
        and not url.password
        and not url.query
        and not url.fragment
    )


def model_author(model):
    name = model.lower().split("/")[-1]
    for prefix, author in (
        ("qwen", "Qwen"),
        ("deepseek", "DeepSeek"),
        ("kimi", "Kimi"),
        ("glm", "GLM"),
        ("minimax", "MiniMax"),
    ):
        if name.startswith(prefix):
            return author
    return ""


def default_model():
    return settings.ai_default_model or settings.ai_model


def resolve_route(value=""):
    route = model_routes().get(value or default_model())
    if route is None:
        raise HTTPException(
            422,
            "This AI model is not enabled on the server. Choose an available model.",
        )
    return route


def available_models():
    return list(model_routes())


def resolve_model(value=""):
    return resolve_route(value).id


def model_catalog():
    routes = model_routes()
    default = routes.get(default_model())
    mock = settings.ai_mode == "mock"
    return {
        "mode": settings.ai_mode,
        "provider": default.provider_label if default else "AI",
        "default_model": default_model(),
        "configured": mock or any(r.configured for r in routes.values()),
        "models": [
            {
                "id": r.id,
                "label": (
                    model_author(r.model) + " · " + r.model
                    if is_bailian_endpoint(r.base_url) and model_author(r.model)
                    else r.model
                ),
                "model_author": model_author(r.model),
                "provider": r.provider,
                "provider_label": r.provider_label,
                "configured": r.configured,
                "available": mock or r.configured,
            }
            for r in routes.values()
        ],
    }
