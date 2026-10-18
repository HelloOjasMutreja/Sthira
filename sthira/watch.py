"""Background watcher: keep the ledger current without anyone uploading anything.

Polls folders (Claude Code's session logs, plus a drop folder for exports and transcripts), and when a file has
changed and then stopped changing, ingests it and extracts from just that file. Polling keeps it dependency-free
and behaves the same on Windows, macOS and Linux.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import api, config, store
from .ingest import parse_path

WATCHED_SUFFIXES = {".json", ".jsonl", ".md", ".txt", ".zip", ".vtt", ".srt"}
SETTLE_SECONDS = 20  # a file still being written (an active agent session) is read once it has been quiet this long


def default_dirs() -> list[Path]:
    """Where AI history usually lands: Claude Code sessions, and a drop folder for exports and transcripts."""
    dirs = [Path.home() / ".claude" / "projects", config.db_path().parent / "inbox"]
    dirs[1].mkdir(parents=True, exist_ok=True)
    return [d for d in dirs if d.exists()]


@dataclass
class Event:
    path: str
    messages: int = 0
    entries: int = 0
    error: str = ""
    alerts: int = 0
    new_entry_ids: list[str] = field(default_factory=list)


def _candidates(dirs: list[Path]):
    for d in dirs:
        for f in d.rglob("*"):
            try:
                if f.is_file() and f.suffix.lower() in WATCHED_SUFFIXES and "node_modules" not in f.parts:
                    st = f.stat()
                    yield str(f), st.st_size, st.st_mtime
            except OSError:
                continue


def scan_once(con: sqlite3.Connection, dirs: list[Path], settle: float = SETTLE_SECONDS, now: float | None = None,
              first_run_backfill: bool = True) -> list[Event]:
    """One pass. Returns what was processed. Files that changed recently wait for the next pass."""
    now = time.time() if now is None else now
    events: list[Event] = []
    known = {r["path"]: (r["size"], r["mtime"]) for r in con.execute("SELECT path, size, mtime FROM watched")}
    if not known and not first_run_backfill:
        # Don't ingest years of history unasked: just remember what's there and react to changes from now on.
        for path, size, mtime in _candidates(dirs):
            con.execute("INSERT OR REPLACE INTO watched(path,size,mtime,seen_at) VALUES (?,?,?,?)", (path, size, mtime, store.now()))
        con.commit()
        return events
    for path, size, mtime in _candidates(dirs):
        if known.get(path) == (size, mtime):
            continue
        if now - mtime < settle:
            continue  # still being written
        name = Path(path).name
        ev = Event(path=path)
        try:
            parsed = parse_path(path)
            ids, msgs = [], 0
            for src_type, key, title, messages in parsed:
                sid = store.upsert_source(con, src_type, key, title)
                msgs += store.add_messages(con, sid, messages)
                ids.append(sid)
            ev.messages = msgs
            if ids and msgs:
                ev.alerts = _check_agent_proposals(con, ids, name)
                created = api.extract(con=con, source_ids=ids)
                ev.entries, ev.new_entry_ids = len(created), [e.id for e in created]
        except Exception as e:  # one bad file must never stop the watcher
            ev.error = f"{type(e).__name__}: {e}"[:200]
        con.execute("INSERT OR REPLACE INTO watched(path,size,mtime,seen_at) VALUES (?,?,?,?)", (path, size, mtime, store.now()))
        con.commit()
        if ev.messages or ev.error:
            events.append(ev)
            _record(con, ev, name)
    return events


MAX_PROPOSALS_CHECKED = 2   # per file per pass: the newest things an agent said it would do
MIN_PROPOSAL_CHARS = 80     # skip "ok" and "done" style replies


def _check_agent_proposals(con: sqlite3.Connection, source_ids: list[str], name: str) -> int:
    """If an agent's newest messages go against a settled decision, raise an alert. Returns how many alerts."""
    if not store.list_entries(con, status="settled"):
        return 0
    marks = ",".join("?" * len(source_ids))
    rows = con.execute(
        f"SELECT text FROM messages WHERE source_id IN ({marks}) AND extracted = 0 AND role = 'assistant' "
        f"AND length(text) >= ? ORDER BY rowid DESC LIMIT ?", [*source_ids, MIN_PROPOSAL_CHARS, MAX_PROPOSALS_CHECKED]
    ).fetchall()
    alerts = 0
    for r in rows:
        verdict = api.check(r["text"][:4000], con=con)
        if verdict.verdict != "contradicts":
            continue
        for c in verdict.conflicts:
            alerts += 1
            store.add_activity(con, "alert", f"An agent in {name} is going against a decision", {
                "agent_said": r["text"][:400], "decision": c.entry.statement, "decided_at": c.entry.decided_at,
                "source": c.entry.source.title, "quote": c.entry.source.quote, "why": c.explanation,
                "entry_id": c.entry.id})
    return alerts


def _record(con: sqlite3.Connection, ev: Event, name: str) -> None:
    if ev.error:
        store.add_activity(con, "error", f"Couldn't read {name}", {"error": ev.error, "path": ev.path})
    else:
        store.add_activity(con, "read", f"Read {name}: {ev.messages} new messages, {ev.entries} to review",
                           {"path": ev.path, "messages": ev.messages, "entries": ev.entries, "alerts": ev.alerts})


def run(dirs: list[Path] | None = None, interval: float = 10.0, on_event=None, stop=None) -> None:
    """Loop until `stop()` returns true. Each pass opens its own connection so it can run in a thread."""
    dirs = dirs or default_dirs()
    while not (stop and stop()):
        con = store.connect()
        try:
            for ev in scan_once(con, dirs, first_run_backfill=False):
                if on_event:
                    on_event(ev)
        finally:
            con.close()
        time.sleep(interval)
