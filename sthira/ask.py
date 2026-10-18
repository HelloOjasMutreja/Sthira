"""Ask your ledger a question and get an answer grounded in it, with citations.

Retrieval is over the entries Sthira has already extracted (settled decisions and their history), so every answer can
point at the exact decision and the exact words you said. If nothing relevant is found, it says so instead of guessing.
"""

from __future__ import annotations

import re
import sqlite3

from . import llm, store
from .models import Entry

SYSTEM = """You answer questions about a person's own decisions, using ONLY the numbered EVIDENCE.
- Answer in one to three short sentences, in plain spoken English, as if talking to them.
- Name the decision and when it was made. If a decision was later replaced, say so.
- Cite the evidence numbers you used in "cited". Never cite a number that is not in the EVIDENCE.
- If the EVIDENCE does not answer the question, say you don't have that in the ledger and cite nothing.
- Never invent decisions, dates or reasons."""

SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}, "cited": {"type": "array", "items": {"type": "integer"}}},
    "required": ["answer", "cited"],
}

RECORD = re.compile(r"^\s*(?:please\s+)?(?:record|note|remember|log|save)(?:\s+that|\s+this)?\s*[:,\-]?\s+(.{8,})$", re.I)
DECIDE = re.compile(r"^\s*(?:we|i)\s*(?:'ve|have)?\s*(?:decided|agreed|chose|will go with|are going with)\s*(?:that|to)?\s*[:,\-]?\s*(.{6,})$", re.I)


def record_intent(text: str) -> str | None:
    """'Record that we use SQLite for search' or 'we decided to use SQLite' -> the decision text, else None."""
    m = RECORD.match(text)
    if m:
        return m.group(1).strip().rstrip(".")
    m = DECIDE.match(text)
    return text.strip().rstrip(".") if m else None  # keep "we decided to ..." whole so the check sees the commitment


def retrieve(con: sqlite3.Connection, question: str, k: int = 8) -> list[Entry]:
    """Settled decisions and their history that match the question; falls back to the most recent settled ones."""
    seen: dict[str, Entry] = {}
    for e in store.list_entries(con, q=question):
        if e.status != "rejected":
            seen.setdefault(e.id, e)
    for e in reversed(store.list_entries(con, status="settled")):
        if len(seen) >= k:
            break
        seen.setdefault(e.id, e)
    return list(seen.values())[:k]


def _fmt(i: int, e: Entry) -> str:
    when = (e.decided_at or "")[:10] or "undated"
    status = "SUPERSEDED (replaced later)" if e.status == "superseded" else e.status
    return (f"[{i}] ({e.kind}, {status}, decided {when}) {e.statement}"
            + (f" Reason: {e.rationale}." if e.rationale else "") + f" Quote: \"{e.source.quote}\"")


def ask(con: sqlite3.Connection, question: str) -> dict:
    """Returns {"answer", "citations": [Entry], "grounded": bool}. Citations are validated against what was retrieved."""
    question = question.strip()[:600]
    cands = retrieve(con, question)
    if not cands:
        return {"answer": "I don't have anything about that in your ledger yet.", "citations": [], "grounded": False}
    evidence = "\n".join(_fmt(i, e) for i, e in enumerate(cands))
    data = llm.chat_json(SYSTEM, f"EVIDENCE:\n{evidence}\n\nQUESTION: {question}", SCHEMA, max_tokens=400)
    answer = (data.get("answer") or "").strip() or "I couldn't work that out from your ledger."
    cited, seen = [], set()
    for n in data.get("cited", []):
        if isinstance(n, int) and 0 <= n < len(cands) and n not in seen:  # a cited number must exist in what we retrieved
            seen.add(n)
            cited.append(cands[n])
    return {"answer": answer, "citations": cited, "grounded": bool(cited)}
