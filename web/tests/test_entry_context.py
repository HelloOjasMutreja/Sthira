"""GET /api/entries/{id}/context: the source conversation around an entry's quote."""

import os
import tempfile

os.environ.setdefault("STHIRA_DB", os.path.join(tempfile.mkdtemp(), "web-test.db"))
os.environ.setdefault("STHIRA_PROVIDER", "ollama")
os.environ.setdefault("OLLAMA_HOST", "http://127.0.0.1:9")

from fastapi.testclient import TestClient  # noqa: E402

from web import app as webapp  # noqa: E402

client = TestClient(webapp.app)


def test_entry_context_marks_the_quoted_message():
    entry = client.get("/api/entries", params={"status": "settled"}).json()[0]
    ctx = client.get(f"/api/entries/{entry['id']}/context", params={"around": 1}).json()
    assert ctx["title"] == entry["source"]["title"]
    matched = [m for m in ctx["messages"] if m["match"]]
    assert len(matched) == 1 and entry["source"]["quote"][:40] in matched[0]["text"]
    assert len(ctx["messages"]) <= 3
    assert all(len(m["text"]) <= 1500 for m in ctx["messages"])


def test_entry_context_unknown_entry_is_404():
    assert client.get("/api/entries/nope/context").status_code == 404


def test_bad_around_is_clamped_not_rejected():
    entry = client.get("/api/entries", params={"status": "settled"}).json()[0]
    assert client.get(f"/api/entries/{entry['id']}/context", params={"around": "abc"}).status_code == 200
    assert client.get(f"/api/entries/{entry['id']}/context", params={"around": 99}).status_code == 200
