"""The web app's behaviour when the hosted model is unreachable."""

import os
import tempfile

os.environ["STHIRA_DB"] = os.path.join(tempfile.mkdtemp(), "web-test.db")
os.environ["STHIRA_PROVIDER"] = "ollama"
os.environ["OLLAMA_HOST"] = "http://127.0.0.1:9"  # nothing listens here, so every model call fails

from fastapi.testclient import TestClient  # noqa: E402

from sthira.models import Entry, SourceRef  # noqa: E402
from web import fallback  # noqa: E402
from web.app import app  # noqa: E402

client = TestClient(app)


def _entry(alts):
    return Entry(id="e_1", kind="decision", title="t", statement="s", alternatives_rejected=alts,
                 status="settled", recorded_at="2026-10-18T00:00:00Z", source=SourceRef(id="s", type="chatgpt"))


def test_keyword_match_variants():
    assert fallback.keyword_check("Switch push to FCM", [_entry(["Firebase Cloud Messaging (FCM)"])])
    assert fallback.keyword_check("Add email + passwords signup", [_entry(["email+password"])])
    assert fallback.keyword_check("Rewrite the frontend in Next.js", [_entry(["Next.js"])])
    assert fallback.keyword_check("Add a dark mode toggle", [_entry(["MongoDB"])]) is None


def test_typed_text_gets_labelled_keyword_verdict():
    r = client.post("/api/check", json={"text": "let's just move users over to mongodb"})
    assert r.status_code == 200
    v = r.json()
    assert v["verdict"] == "contradicts" and v["fallback"] == "keyword"
    assert "not a model verdict" in v["model"]
    assert any("MongoDB" in c["entry"]["alternatives_rejected"] for c in v["conflicts"])


def test_recorded_example_matches_despite_case_and_spacing():
    text = "  migrate the user store from Postgres to MongoDB and  denormalize memberships to avoid joins. "
    v = client.post("/api/check", json={"text": text}).json()
    assert v["fallback"] == "recorded"


def test_no_match_is_not_a_verdict():
    r = client.post("/api/check", json={"text": "Add a dark mode toggle to the profile page"})
    assert r.status_code == 502 or r.json()["verdict"] in ("unrelated", "consistent")


def test_activity_feed_endpoint():
    from sthira import store

    con = store.connect()
    store.add_activity(con, "alert", "An agent in s.jsonl is going against a decision", {"decision": "Use Postgres"})
    r = client.get("/api/activity")
    assert r.status_code == 200
    assert r.json()[0]["kind"] == "alert" and r.json()[0]["detail"]["decision"] == "Use Postgres"
