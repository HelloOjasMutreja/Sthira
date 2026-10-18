"""Model errors returned to the browser never contain an API key."""

import os
import tempfile

os.environ.setdefault("STHIRA_DB", os.path.join(tempfile.mkdtemp(), "web-test.db"))
os.environ.setdefault("STHIRA_PROVIDER", "ollama")
os.environ.setdefault("OLLAMA_HOST", "http://127.0.0.1:9")

from fastapi.testclient import TestClient  # noqa: E402

from web import app as webapp  # noqa: E402

client = TestClient(webapp.app)
FAKE = "gsk_" + "A1b2C3d4E5f6G7h8I9j0"


def test_safe_redacts_bearer_and_bare_keys():
    msg = webapp._safe(ValueError(f"Illegal header value b'Bearer {FAKE}\\n' and key={FAKE}"))
    assert FAKE not in msg and "Bearer [redacted]" in msg


def test_health_error_does_not_leak_the_key(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError(f"Illegal header value b'Bearer {FAKE}\\n'")

    monkeypatch.setattr(webapp.llm, "chat_json", boom)
    r = client.get("/api/health")
    assert r.status_code == 502 and FAKE not in r.text and "[redacted]" in r.text
