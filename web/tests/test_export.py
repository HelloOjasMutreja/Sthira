"""GET /api/export: the whole ledger as a JSON or Markdown download."""

import os
import tempfile

os.environ.setdefault("STHIRA_DB", os.path.join(tempfile.mkdtemp(), "web-test.db"))
os.environ.setdefault("STHIRA_PROVIDER", "ollama")
os.environ.setdefault("OLLAMA_HOST", "http://127.0.0.1:9")  # nothing listens here, so real model calls fail

from fastapi.testclient import TestClient  # noqa: E402

from web import app as webapp  # noqa: E402

client = TestClient(webapp.app)


def test_json_export_has_every_entry():
    r = client.get("/api/export", params={"format": "json"})
    assert r.status_code == 200
    assert r.headers["content-disposition"] == 'attachment; filename="sthira-ledger.json"'
    body = r.json()
    assert body["format"] == "sthira-ledger/1"
    assert {e["id"] for e in body["entries"]} == {e["id"] for e in client.get("/api/entries").json()}
    assert body["entries"] and {"id", "status", "statement", "source"} <= set(body["entries"][0])


def test_json_is_the_default_format():
    r = client.get("/api/export")
    assert r.status_code == 200 and r.json()["format"] == "sthira-ledger/1"


def test_export_keeps_superseded_and_rejected_entries(monkeypatch, tmp_path):
    monkeypatch.setenv("STHIRA_DB", str(tmp_path / "export.db"))  # a fresh seeded ledger, so other tests are unaffected
    entries = client.get("/api/entries").json()
    settled, other = [e for e in entries if e["status"] == "settled"][:2]
    client.post(f"/api/entries/{other['id']}/review", json={"action": "reject", "note": "not a decision"})
    new = client.post(f"/api/entries/{settled['id']}/replace",
                      json={"statement": "Use SQLite for the export test", "rationale": "test"}).json()["new"]
    statuses = {e["id"]: e["status"] for e in client.get("/api/export").json()["entries"]}
    assert statuses[other["id"]] == "rejected" and statuses[settled["id"]] == "superseded"

    md = client.get("/api/export", params={"format": "md"}).text
    assert "## Superseded" in md and "## Rejected" in md
    assert f"- **Superseded by:** {new['id']}" in md


def test_markdown_export_groups_by_status_and_quotes_the_source():
    r = client.get("/api/export", params={"format": "md"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    assert r.headers["content-disposition"] == 'attachment; filename="sthira-ledger.md"'
    md = r.text
    assert md.startswith("# Sthira ledger") and "## Settled" in md
    e = next(e for e in client.get("/api/entries", params={"status": "settled"}).json() if e["source"]["quote"])
    assert f"- **Statement:** {' '.join(e['statement'].split())}" in md
    assert f"> {e['source']['quote'].splitlines()[0]}" in md
    assert "- **Kind:** " in md and "- **Source:** " in md


def test_unknown_format_is_rejected():
    for fmt in ("pdf", "csv", ""):
        assert client.get("/api/export", params={"format": fmt}).status_code == 400
