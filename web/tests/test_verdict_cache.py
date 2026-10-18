"""The verdict cache on POST /api/check: repeated checks reuse the model's verdict until the ledger or feedback changes."""

import os
import tempfile

os.environ.setdefault("STHIRA_DB", os.path.join(tempfile.mkdtemp(), "web-test.db"))
os.environ.setdefault("STHIRA_PROVIDER", "ollama")
os.environ.setdefault("OLLAMA_HOST", "http://127.0.0.1:9")  # nothing listens here, so real model calls fail

from fastapi.testclient import TestClient  # noqa: E402

from sthira.models import Verdict  # noqa: E402
from web import app as webapp  # noqa: E402

client = TestClient(webapp.app)


def test_repeated_check_is_cached_until_feedback_changes(monkeypatch):
    calls = []

    def fake_check(text, con=None):
        calls.append(text)
        return Verdict(input=text, verdict="unrelated", conflicts=[], model="test-model")

    monkeypatch.setattr(webapp.api, "check", fake_check)
    webapp._verdict_cache.clear()
    text = "Add a CSV export button to the notes list"
    first = client.post("/api/check", json={"text": text}).json()
    second = client.post("/api/check", json={"text": "  add a csv export button to the NOTES list "}).json()
    assert len(calls) == 1 and "cached" not in first and second["cached"] is True

    client.post("/api/correct", json={"text": text, "note": "exports are fine"})
    third = client.post("/api/check", json={"text": text}).json()
    assert len(calls) == 2 and "cached" not in third


def test_fallback_verdicts_are_not_cached():
    webapp._verdict_cache.clear()
    client.post("/api/check", json={"text": "let's just move users over to mongodb"})
    assert not webapp._verdict_cache
