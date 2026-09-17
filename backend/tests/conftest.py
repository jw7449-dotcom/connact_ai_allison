import os
import tempfile
from pathlib import Path

# Explicit isolated test database; never use the running personal workspace DB.
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "sqlite:///" + str(Path(tempfile.mkdtemp()) / "test.db")
)
os.environ["UPLOAD_DIR"] = tempfile.mkdtemp()
os.environ["PEOPLE_MODE"] = "mock"
os.environ["AI_MODE"] = "mock"
os.environ["AI_PROVIDERS"] = "[]"
os.environ["AI_DEFAULT_MODEL"] = ""
for key in ("OPENAI_API_KEY", "DEEPSEEK_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "DASHSCOPE_API_KEY"):
    os.environ[key] = ""
os.environ["PUBLIC_SEARCH_MODE"] = "mock"
os.environ["AUTH_MODE"] = "local"
os.environ["AUTH_PROVIDER"] = "password"
os.environ["GOOGLE_CLIENT_ID"] = ""
os.environ["GOOGLE_CLIENT_SECRET"] = ""
os.environ["GMAIL_CLIENT_ID"] = ""
os.environ["GMAIL_CLIENT_SECRET"] = ""
os.environ["GMAIL_TOKEN_ENCRYPTION_KEYS"] = ""
os.environ["GMAIL_WORKER_ENABLED"] = "false"
os.environ["PUBLIC_ORIGIN"] = "http://127.0.0.1:3100"
# Contract tests must never pick up real credentials from the local .env.
for key in ("SERPAPI_API_KEY", "APOLLO_API_KEY", "AI_API_KEY", "APIFY_API_KEY", "APIFY_API_TOKEN"):
    os.environ[key] = ""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base, engine


@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as c:
        yield c
