"""Stable Python API used by the CLI, the MCP server and the web app (see docs/CONTRACTS.md)."""

from __future__ import annotations

from . import check as _check
from . import extract as _extract
from . import feedback as _feedback
from . import store
from . import sync as _sync
from .ingest import parse_bytes, parse_path
from .models import Entry, Verdict


def _ingest_results(con, results) -> dict:
    messages, ids = 0, []
    for src_type, key, title, msgs in results:
        sid = store.upsert_source(con, src_type, key, title)
        messages += store.add_messages(con, sid, msgs)
        ids.append(sid)
    return {"sources": len(ids), "messages": messages, "source_ids": ids}


def ingest(path: str, kind: str | None = None, con=None) -> dict:
    con = con or store.connect()
    return _ingest_results(con, parse_path(path, kind))


def ingest_upload(filename: str, data: bytes, kind: str | None = None, con=None) -> dict:
    con = con or store.connect()
    return _ingest_results(con, parse_bytes(filename, data, kind))


def extract(limit: int | None = None, con=None, on_progress=None, source_ids: list[str] | None = None,
            errors: list[str] | None = None, on_chunk=None) -> list[Entry]:
    """Extract from pending conversations (oldest first); pass source_ids to only read those sources."""
    con = con or store.connect()
    return _extract.extract(con, limit, on_progress, source_ids=source_ids, errors=errors, on_chunk=on_chunk)


def list_entries(status: str | None = None, kind: str | None = None, q: str | None = None, con=None) -> list[Entry]:
    con = con or store.connect()
    return store.list_entries(con, status, kind, q)


def review(entry_id: str, action: str, note: str | None = None, con=None) -> Entry:
    """settle: confirm the entry; reject: it was a bad extraction (Sthira learns from it)."""
    con = con or store.connect()
    if action not in ("settle", "reject"):
        raise ValueError("action must be 'settle' or 'reject'")
    e = store.set_status(con, entry_id, "settled" if action == "settle" else "rejected",
                         trust="confirmed" if action == "settle" else "quarantined")
    store.add_feedback(con, "extraction", action, entry_id, note, e.statement)
    return e


def supersede(old_id: str, new_id: str, con=None) -> Entry:
    con = con or store.connect()
    if old_id == new_id:
        raise ValueError("an entry can't supersede itself")
    for i in (old_id, new_id):  # validate both before writing anything
        if store.get_entry(con, i) is None:
            raise KeyError(i)
    store.set_status(con, new_id, "settled", trust="confirmed")
    return store.set_status(con, old_id, "superseded", superseded_by=new_id)


def replace(old_id: str, statement: str, rationale: str = "", con=None) -> dict:
    """Deliberately change your mind: record the new decision as settled and supersede the old one (kept as history)."""
    con = con or store.connect()
    old = store.get_entry(con, old_id)
    if old is None:
        raise KeyError(old_id)
    new = propose(statement, kind=old.kind, rationale=rationale, title=old.title, source_title="changed in Sthira", con=con)
    new = store.set_status(con, new.id, "settled", trust="confirmed")
    old = store.set_status(con, old_id, "superseded", superseded_by=new.id)
    return {"old": old, "new": new}


def propose(statement: str, kind: str = "decision", rationale: str = "", title: str = "",
            source_title: str = "manual", con=None) -> Entry:
    """Record a new entry directly (e.g. from an agent over MCP). Starts quarantined until a human settles it."""
    from .models import SourceRef

    con = con or store.connect()
    e = Entry(id=store.new_id("e"), kind=kind, title=title or statement[:60], statement=statement, rationale=rationale,
              status="proposed", trust="quarantined", decided_at=store.now(), recorded_at=store.now(),
              source=SourceRef(id="manual", type="manual", title=source_title, locator="", quote=statement[:300]))
    return store.insert_entry(con, e)


def check(text: str, con=None) -> Verdict:
    con = con or store.connect()
    return _check.check(con, text)


def scan(path: str, con=None, max_messages: int = 8) -> list[dict]:
    """Check what an AI agent proposed in a session transcript against the ledger."""
    con = con or store.connect()
    out = []
    for _src, _key, _title, msgs in parse_path(path):
        proposals = [m for m in msgs if m.role == "assistant" and len(m.text) > 40][-max_messages:]
        for m in proposals:
            out.append({"msg_id": m.msg_id, "text": m.text, "verdict": _check.check(con, m.text)})
    return out


def correct_check(text: str, note: str, con=None) -> None:
    """User says a verdict was wrong; the note is fed into future checks."""
    con = con or store.connect()
    store.add_feedback(con, "check", "override", None, note, text)


def learned_rules(con=None) -> list[dict]:
    """The rules Sthira learned from your rejections and verdict corrections (applied on every future run)."""
    con = con or store.connect()
    return _feedback.learned_rules(con)


def recent_activity(limit: int = 30, con=None) -> list[dict]:
    """What the background watcher did: files read, entries waiting for review, and agents caught going against decisions."""
    con = con or store.connect()
    return store.recent_activity(con, limit)


def mark_activity_seen(con=None) -> None:
    """The user has looked at the activity feed: alerts so far stop counting as unseen."""
    con = con or store.connect()
    store.mark_activity_seen(con)


def feedback_stats(con=None) -> dict:
    con = con or store.connect()
    return _feedback.stats(con)


def sync(path: str | None = None, con=None, fmt: str = "agents") -> str:
    """fmt='agents' updates a managed block in AGENTS.md/CLAUDE.md; fmt='cursor' writes .cursor/rules/sthira.mdc."""
    con = con or store.connect()
    if fmt == "cursor":
        return _sync.sync_cursor(con, path or _sync.CURSOR_RULE)
    return _sync.sync(con, path or "AGENTS.md")
