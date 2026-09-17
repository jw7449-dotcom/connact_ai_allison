import importlib
import json
import httpx
import pytest
from fastapi import HTTPException
from app.config import settings, AIProviderConfig
from app.providers.ai import CompatibleAI
from app.providers.model_registry import model_catalog, resolve_model


@pytest.fixture
def live(monkeypatch):
    # Optional routes are explicit test configuration, not default product choices.
    monkeypatch.setattr(
        settings,
        "ai_providers",
        [
            AIProviderConfig(
                id="openai",
                label="OpenAI",
                base_url="https://api.openai.com/v1",
                api_key_env="OPENAI_API_KEY",
                models=["gpt-4.1-mini", "gpt-4.1"],
                token_parameter="max_completion_tokens",
            ),
            AIProviderConfig(
                id="deepseek",
                label="DeepSeek",
                base_url="https://api.deepseek.com",
                api_key_env="DEEPSEEK_API_KEY",
                models=["deepseek-v4-flash", "deepseek-v4-pro"],
            ),
            AIProviderConfig(
                id="google",
                label="Google Gemini",
                base_url="https://generativelanguage.googleapis.com/v1beta/openai",
                api_key_env="GEMINI_API_KEY",
                models=["gemini-3.8-flash"],
            ),
            AIProviderConfig(
                id="anthropic",
                label="Anthropic Claude",
                base_url="https://api.anthropic.com/v1",
                api_key_env="ANTHROPIC_API_KEY",
                models=["claude-sonnet-4-6", "claude-opus-5"],
                protocol="anthropic",
            ),
            AIProviderConfig(
                id="qwen",
                label="Alibaba Qwen",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                api_key_env="DASHSCOPE_API_KEY",
                models=["qwen-plus", "qwen-turbo", "qwen-max"],
            ),
        ],
    )
    monkeypatch.setattr(settings, "ai_mode", "live")
    monkeypatch.setattr(settings, "ai_api_key", "legacy-test-key")
    for field in (
        "openai_api_key",
        "deepseek_api_key",
        "gemini_api_key",
        "anthropic_api_key",
        "dashscope_api_key",
    ):
        monkeypatch.setattr(settings, field, field + "-test-only")


@pytest.mark.parametrize(
    "model,host,key_field,token_field",
    [
        (
            "openai/gpt-4.1-mini",
            "api.openai.com",
            "openai_api_key",
            "max_completion_tokens",
        ),
        (
            "deepseek/deepseek-v4-flash",
            "api.deepseek.com",
            "deepseek_api_key",
            "max_tokens",
        ),
        (
            "google/gemini-3.8-flash",
            "generativelanguage.googleapis.com",
            "gemini_api_key",
            "max_tokens",
        ),
        ("qwen/qwen-plus", "dashscope.aliyuncs.com", "dashscope_api_key", "max_tokens"),
        (
            "bailian/deepseek-v4-flash",
            "dashscope.aliyuncs.com",
            "dashscope_api_key",
            "max_tokens",
        ),
        (
            "bailian/kimi-k3",
            "dashscope.aliyuncs.com",
            "dashscope_api_key",
            "max_tokens",
        ),
        (
            "bailian/glm-5.2",
            "dashscope.aliyuncs.com",
            "dashscope_api_key",
            "max_tokens",
        ),
        (
            "bailian/MiniMax-M2.5",
            "dashscope.aliyuncs.com",
            "dashscope_api_key",
            "max_tokens",
        ),
        (
            "anthropic/claude-sonnet-4-6",
            "api.anthropic.com",
            "anthropic_api_key",
            "max_tokens",
        ),
    ],
)
def test_actual_http_routes_and_credentials(
    live, monkeypatch, model, host, key_field, token_field
):
    calls = []

    def handle(req):
        calls.append(req)
        assert req.url.host == host
        body = json.loads(req.content)
        assert body["model"] == model.split("/", 1)[1]
        assert body[token_field] == 2400
        assert ("enable_thinking" in body) == (
            host == "dashscope.aliyuncs.com" and "MiniMax" not in model
        )
        assert "_model" not in req.content.decode()
        key = getattr(settings, key_field)
        if host == "api.anthropic.com":
            assert req.url.path == "/v1/messages"
            assert req.headers["x-api-key"] == key
            assert "authorization" not in req.headers
            assert req.headers["anthropic-version"] == "2023-06-01"
            assert "UNTRUSTED" in body["system"]
            assert "response_format" not in body
            return httpx.Response(
                200,
                json={
                    "content": [
                        {
                            "type": "text",
                            "text": '```json\n{"subject":"Hi","body_html":"<p>Hello</p>"}\n```',
                        }
                    ]
                },
            )
        assert req.headers["authorization"] == "Bearer " + key
        assert req.url.path.endswith("/chat/completions")
        assert body["response_format"] == {"type": "json_object"}
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"subject":"Hi","body_html":"<p>Hello</p>"}'
                        }
                    }
                ]
            },
        )

    original = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kw: original(transport=httpx.MockTransport(handle), **kw),
    )
    assert CompatibleAI().complete("generate", {"_model": model})["subject"] == "Hi"
    assert len(calls) == 1


def test_catalog_hides_secrets_and_tracks_each_model(live, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(settings, "ai_default_model", "deepseek/deepseek-v4-flash")
    catalog = model_catalog()
    assert catalog["default_model"] == resolve_model() == "deepseek/deepseek-v4-flash"
    models = {m["id"]: m for m in catalog["models"]}
    assert models["google/gemini-3.8-flash"]["available"] is False
    assert models["deepseek/deepseek-v4-flash"]["available"] is True
    encoded = json.dumps(catalog)
    assert (
        "test-only" not in encoded
        and "base_url" not in encoded
        and "api_key" not in encoded
    )
    monkeypatch.setattr(settings, "ai_mode", "mock")
    assert all(m["available"] for m in model_catalog()["models"])


def test_missing_provider_key_never_uses_legacy_key(live, monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "")

    def forbidden(**kwargs):
        pytest.fail("A missing provider key must not issue a request")

    monkeypatch.setattr(httpx, "Client", forbidden)
    with pytest.raises(HTTPException) as error:
        CompatibleAI().complete("generate", {"_model": "openai/gpt-4.1-mini"})
    assert error.value.status_code == 503


def test_unknown_model_and_custom_provider(live, monkeypatch):
    with pytest.raises(HTTPException) as error:
        resolve_model("other/unapproved")
    assert error.value.status_code == 422
    monkeypatch.setenv("CUSTOM_AI_KEY", "custom-test-only")
    monkeypatch.setattr(
        settings,
        "ai_providers",
        [
            AIProviderConfig(
                id="gateway",
                label="Company gateway",
                base_url="https://gateway.example/v1",
                api_key_env="CUSTOM_AI_KEY",
                models=["vendor/model"],
                json_mode=False,
            )
        ],
    )
    ai = importlib.import_module("app.providers.ai")

    def request(provider, method, url, key, **kwargs):
        assert url == "https://gateway.example/v1/chat/completions"
        assert key == "custom-test-only"
        assert kwargs["json"]["model"] == "vendor/model"
        assert "response_format" not in kwargs["json"]
        return {"choices": [{"message": {"content": '{"dimensions":[]}'}}]}

    monkeypatch.setattr(ai, "request_json", request)
    assert CompatibleAI().complete("assess", {"_model": "gateway/vendor/model"}) == {
        "dimensions": []
    }


def test_selected_model_survives_writing_job(client, monkeypatch):
    from app.db import Session
    from app.models import WritingJob
    from app.services.drafts import process_writing_job, stop_writing_worker

    stop_writing_worker()
    model = "bailian/deepseek-v4-flash"
    draft = client.post(
        "/api/drafts", json={"purpose": "Connect", "model": model}
    ).json()
    job = client.post(
        f'/api/drafts/{draft["id"]}/generations',
        json={"action": "generate", "revision": draft["revision"]},
    )
    assert job.status_code == 202, job.text
    assert job.json()["model"] == model
    process_writing_job(job.json()["id"])
    with Session() as db:
        saved = db.get(WritingJob, job.json()["id"])
        assert saved.model == model and saved.status == "succeeded"


def test_unconfigured_model_rejected_before_queue(client, monkeypatch):
    monkeypatch.setattr(settings, "ai_mode", "live")
    monkeypatch.setattr(settings, "dashscope_api_key", "")
    monkeypatch.setattr(settings, "ai_api_key", "")
    draft = client.post(
        "/api/drafts", json={"purpose": "Connect", "model": "bailian/deepseek-v4-flash"}
    ).json()
    response = client.post(
        f'/api/drafts/{draft["id"]}/generations',
        json={"action": "generate", "revision": draft["revision"]},
    )
    assert response.status_code == 503
    assert client.get(f'/api/drafts/{draft["id"]}/generations').json() == []


def test_bailian_shared_key_keeps_direct_vendor_credentials_separate(live, monkeypatch):
    from app.providers.model_registry import resolve_route

    monkeypatch.setattr(
        settings, "ai_base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    monkeypatch.setattr(settings, "dashscope_api_key", "")
    monkeypatch.setattr(settings, "deepseek_api_key", "")
    for model in ("deepseek-v4-flash", "kimi-k3", "glm-5.2", "MiniMax-M2.5"):
        assert resolve_route("bailian/" + model).api_key == "legacy-test-key"
    assert not resolve_route("deepseek/deepseek-v4-flash").configured
    rows = {m["id"]: m for m in model_catalog()["models"]}
    assert rows["bailian/kimi-k3"]["model_author"] == "Kimi"
    assert rows["bailian/kimi-k3"]["available"] is True
    monkeypatch.setattr(settings, "ai_base_url", "https://other.example/v1")
    assert not resolve_route("bailian/kimi-k3").configured


def test_bailian_override_cannot_reuse_key_for_untrusted_endpoint(live, monkeypatch):
    from app.providers.model_registry import resolve_route

    monkeypatch.setattr(settings, "dashscope_api_key", "")
    endpoint = "https://dashscope.aliyuncs.com.evil.example/compatible-mode/v1"
    monkeypatch.setattr(settings, "ai_base_url", endpoint)
    monkeypatch.setattr(
        settings,
        "ai_providers",
        [
            AIProviderConfig(
                id="bailian",
                label="Bailian",
                base_url=endpoint,
                api_key_env="DASHSCOPE_API_KEY",
                models=["kimi-k3"],
            )
        ],
    )
    assert not resolve_route("bailian/kimi-k3").configured
