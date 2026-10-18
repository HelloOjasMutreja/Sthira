"""GET /api/demo-session: the Claude Code session the in-browser agent replay types out."""

import os
import tempfile

os.environ.setdefault("STHIRA_DB", os.path.join(tempfile.mkdtemp(), "web-test.db"))
os.environ.setdefault("STHIRA_PROVIDER", "ollama")
os.environ.setdefault("OLLAMA_HOST", "http://127.0.0.1:9")  # nothing listens here, so real model calls fail

from fastapi.testclient import TestClient  # noqa: E402

from web import app as webapp  # noqa: E402

client = TestClient(webapp.app)


def test_demo_session_is_the_parsed_claude_code_session():
    r = client.get("/api/demo-session")
    assert r.status_code == 200
    s = r.json()
    assert s["title"]
    assert [m["role"] for m in s["messages"]] == ["user", "assistant", "user", "assistant"]
    assert all(set(m) == {"role", "text"} and m["text"] for m in s["messages"])
    agent = [m["text"] for m in s["messages"] if m["role"] == "assistant"]
    assert any("MongoDB" in t for t in agent) and any("email+password" in t for t in agent)


def test_each_agent_message_is_caught_without_the_model():
    # The replay checks every agent message; with the model unreachable, the labelled keyword fallback catches both.
    webapp._verdict_cache.clear()
    for m in client.get("/api/demo-session").json()["messages"]:
        if m["role"] == "assistant" and len(m["text"]) > 40:
            v = client.post("/api/check", json={"text": m["text"]}).json()
            assert v["verdict"] == "contradicts" and v["fallback"] == "keyword"
