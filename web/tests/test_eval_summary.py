"""GET /api/eval: the evidence panel's numbers, which must match eval/README.md exactly."""

import os
import re
import tempfile
from pathlib import Path

os.environ.setdefault("STHIRA_DB", os.path.join(tempfile.mkdtemp(), "web-test.db"))
os.environ.setdefault("STHIRA_PROVIDER", "ollama")
os.environ.setdefault("OLLAMA_HOST", "http://127.0.0.1:9")  # nothing listens here, so real model calls fail

from fastapi.testclient import TestClient  # noqa: E402

from web import app as webapp  # noqa: E402

client = TestClient(webapp.app)
README = (Path(__file__).resolve().parents[2] / "eval" / "README.md").read_text(encoding="utf-8")


def _row(*cells: str) -> bool:
    """True if a README table row contains these cells in order (bold markers ignored)."""
    plain = README.replace("**", "")
    return any(all(c in line for c in cells) and line.index(cells[0]) < line.index(cells[-1])
               for line in plain.splitlines() if line.startswith("|"))


def test_eval_endpoint_serves_the_summary():
    r = client.get("/api/eval")
    assert r.status_code == 200
    ev = r.json()
    assert ev["source"] == "eval/README.md" and ev["url"].endswith("/eval/README.md")
    assert {"extraction", "checks", "dogfood", "limits"} <= set(ev)
    assert ev["limits"] and all(isinstance(s, str) and s for s in ev["limits"])


def test_extraction_numbers_match_the_readme():
    ex = client.get("/api/eval").json()["extraction"]
    for row in ex["rows"]:
        assert _row(row["model"], f"{row['before']:.2f}", f"{row['after']:.2f}", f"{row['recall']:.2f}",
                    f"{row['caught']} / {row['drifts']}"), row
    head = [r for r in ex["rows"] if r.get("headline")]
    assert len(head) == 1
    assert {k: head[0][k] for k in ("model", "before", "after", "recall")} == ex["headline"]
    assert "run 2, current prompt" in head[0]["run"]


def test_check_numbers_match_the_readme():
    ch = client.get("/api/eval").json()["checks"]
    single, critic = ch["rows"]
    assert (single["correct"], single["total"], critic["correct"], critic["total"]) == (4, 6, 6, 6)
    assert critic["winner"] and not single.get("winner")
    for row in ch["rows"]:
        assert _row(ch["model"], row["pipeline"].lower(), f"{row['correct']} / {row['total']}", row["latency"]), row


def test_dogfood_matches_the_readme():
    dog = client.get("/api/eval").json()["dogfood"]
    assert re.search(rf"\b{dog['messages']} messages, qwen3\.8-27b", README)
    assert f"**{dog['entries']} entries**" in README
    assert all(f'"{d}' in README for d in dog["right"])  # quoted verbatim from the decisions it found
    assert dog["wrong"] and "17 of 143" in dog["bug"] and "17 of 143" in README
