import json
import os
import tempfile

os.environ["STHIRA_DB"] = os.path.join(tempfile.mkdtemp(), "stream.db")
os.environ["STHIRA_PROVIDER"] = "ollama"

import pytest  # noqa: E402

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from sthira import llm  # noqa: E402
from web.app import app  # noqa: E402

client = TestClient(app)
ENTRY = {"kind": "decision", "title": "Use SQLite", "statement": "Use SQLite for search.", "rationale": "small",
         "alternatives_rejected": [], "quote": "we use SQLite for search", "msg": 0, "confidence": 0.9}


def _events(resp):
    return [json.loads(line) for line in resp.text.splitlines() if line.strip()]


def test_stream_reports_parsed_then_chunks_then_done(monkeypatch):
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: {"entries": [ENTRY]})
    r = client.post("/api/import/stream", files={"file": ("2026-10-18-plan.md", b"Ojas: we use SQLite for search.\n")})
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/x-ndjson")
    ev = _events(r)
    kinds = [e["event"] for e in ev]
    assert kinds[0] == "parsed" and kinds[-1] == "done" and "chunk" in kinds
    assert ev[0]["messages"] == 1 and ev[0]["seconds_per_chunk_hint"] > 0
    chunk = next(e for e in ev if e["event"] == "chunk" and e["phase"] == "read")
    assert chunk["done"] == chunk["total"] == 1 and chunk["found"][0]["statement"] == "Use SQLite for search."
    assert ev[-1]["entries"][0]["statement"] == "Use SQLite for search."


def test_stream_reports_a_model_failure_instead_of_dropping_the_connection(monkeypatch):
    def boom(*a, **k):
        raise llm.LLMUnavailable("Can't reach Ollama")

    monkeypatch.setattr(llm, "chat_json", boom)
    r = client.post("/api/import/stream", files={"file": ("2026-10-18-other.md", b"Danica: we use Redis for cache.\n")})
    ev = _events(r)
    assert ev[-1]["event"] == "error" and "Ollama" in ev[-1]["message"]
