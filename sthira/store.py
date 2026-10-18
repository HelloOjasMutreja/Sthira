"""SQLite storage: sources, messages, ledger entries, feedback. Nothing in the ledger is ever deleted."""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .models import Entry, Message, SourceRef

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    title TEXT,
    path TEXT,
    UNIQUE(type, path)
);
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(id),
    conv_id TEXT NOT NULL,
    conv_title TEXT,
    msg_id TEXT NOT NULL,
    role TEXT,
    ts TEXT,
    text TEXT NOT NULL,
    extracted INTEGER NOT NULL DEFAULT 0,
    UNIQUE(source_id, conv_id, msg_id)
);
CREATE TABLE IF NOT EXISTS entries (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    statement TEXT NOT NULL,
    rationale TEXT,
    alternatives_rejected TEXT,
    project TEXT,
    status TEXT NOT NULL,
    trust TEXT NOT NULL,
    superseded_by TEXT,
    decided_at TEXT,
    recorded_at TEXT NOT NULL,
    source_json TEXT NOT NULL,
    confidence REAL,
    run_id TEXT
);
CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(id UNINDEXED, title, statement, rationale);
CREATE TABLE IF NOT EXISTS feedback (
    id TEXT PRIMARY KEY,
    entry_id TEXT,
    target TEXT NOT NULL,          -- 'extraction' or 'check'
    action TEXT NOT NULL,          -- settle / reject / override
    note TEXT,
    snippet TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS watched (
    path TEXT PRIMARY KEY,
    size INTEGER NOT NULL,
    mtime REAL NOT NULL,
    seen_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    kind TEXT NOT NULL,            -- 'read' | 'alert' | 'error'
    title TEXT NOT NULL,
    detail TEXT                    -- JSON
);
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    started_at TEXT NOT NULL,
    feedback_count INTEGER NOT NULL
);
"""


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    con = sqlite3.connect(str(path or config.db_path()))
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


# ---- sources & messages -------------------------------------------------

def upsert_source(con: sqlite3.Connection, type_: str, path: str, title: str) -> str:
    row = con.execute("SELECT id FROM sources WHERE type=? AND path=?", (type_, path)).fetchone()
    if row:
        return row["id"]
    sid = new_id("s")
    con.execute("INSERT INTO sources(id,type,title,path) VALUES (?,?,?,?)", (sid, type_, title, path))
    return sid


def add_messages(con: sqlite3.Connection, source_id: str, msgs: list[Message]) -> int:
    n = 0
    for m in msgs:
        if not m.text.strip():
            continue
        cur = con.execute(
            "INSERT OR IGNORE INTO messages(id,source_id,conv_id,conv_title,msg_id,role,ts,text) VALUES (?,?,?,?,?,?,?,?)",
            (new_id("m"), source_id, m.conv_id, m.conv_title, m.msg_id, m.role, m.ts, m.text),
        )
        n += cur.rowcount
    con.commit()
    return n


def pending_conversations(con: sqlite3.Connection, source_ids: list[str] | None = None) -> list[dict]:
    """Conversations that have messages not yet extracted, oldest conversation first.
    A conversation is identified by (source, conv_id), so two sources sharing a conv_id never mix."""
    where, args = "", []
    if source_ids is not None:
        if not source_ids:
            return []
        where = f" AND m.source_id IN ({','.join('?' * len(source_ids))})"
        args = list(source_ids)
    rows = con.execute(
        f"""SELECT m.*, s.type AS source_type, s.title AS source_title, p.first_seen FROM messages m
           JOIN sources s ON s.id = m.source_id
           JOIN (SELECT source_id, conv_id, MIN(COALESCE(ts, '')) AS first_seen, MIN(rowid) AS first_row FROM messages
                 GROUP BY source_id, conv_id HAVING SUM(extracted = 0) > 0) p
             ON p.source_id = m.source_id AND p.conv_id = m.conv_id
           WHERE 1 = 1{where}
           ORDER BY p.first_seen, p.first_row, COALESCE(m.ts, ''), m.rowid""", args
    ).fetchall()
    convs: dict[tuple, dict] = {}
    for r in rows:
        key = (r["source_id"], r["conv_id"])
        c = convs.setdefault(key, {
            "source_id": r["source_id"], "source_type": r["source_type"], "conv_id": r["conv_id"],
            "conv_title": r["conv_title"] or r["source_title"] or r["conv_id"], "messages": [],
        })
        c["messages"].append(dict(r))
    for c in convs.values():
        c["messages"] = _with_context(c["messages"])
    return list(convs.values())


CONTEXT_MESSAGES = 2


def _with_context(msgs: list[dict]) -> list[dict]:
    """Only what's new, plus the couple of messages before it so 'ok, go with that' still has something to refer to.
    Without this, one new message in a long session would send the whole session to the model again."""
    keep = set()
    for i, m in enumerate(msgs):
        if not m["extracted"]:
            keep.update(range(max(0, i - CONTEXT_MESSAGES), i + 1))
    return [m for i, m in enumerate(msgs) if i in keep]


def mark_extracted(con: sqlite3.Connection, message_ids: list[str]) -> None:
    con.executemany("UPDATE messages SET extracted = 1 WHERE id = ?", [(i,) for i in message_ids])
    con.commit()


# ---- entries --------------------------------------------------------------

def _row_to_entry(r: sqlite3.Row) -> Entry:
    return Entry(
        id=r["id"], kind=r["kind"], title=r["title"], statement=r["statement"], rationale=r["rationale"] or "",
        alternatives_rejected=json.loads(r["alternatives_rejected"] or "[]"), project=r["project"] or "",
        status=r["status"], trust=r["trust"], superseded_by=r["superseded_by"], decided_at=r["decided_at"],
        recorded_at=r["recorded_at"], source=SourceRef(**json.loads(r["source_json"])), confidence=r["confidence"] or 0.5,
    )


def insert_entry(con: sqlite3.Connection, e: Entry, run_id: str | None = None) -> Entry:
    con.execute(
        """INSERT INTO entries(id,kind,title,statement,rationale,alternatives_rejected,project,status,trust,
           superseded_by,decided_at,recorded_at,source_json,confidence,run_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (e.id, e.kind, e.title, e.statement, e.rationale, json.dumps(e.alternatives_rejected), e.project, e.status,
         e.trust, e.superseded_by, e.decided_at, e.recorded_at, e.source.model_dump_json(), e.confidence, run_id),
    )
    con.execute("INSERT INTO entries_fts(id,title,statement,rationale) VALUES (?,?,?,?)",
                (e.id, e.title, e.statement, e.rationale))
    con.commit()
    return e


def get_entry(con: sqlite3.Connection, entry_id: str) -> Entry | None:
    r = con.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
    return _row_to_entry(r) if r else None


def list_entries(con: sqlite3.Connection, status: str | None = None, kind: str | None = None,
                 q: str | None = None) -> list[Entry]:
    sql, args = "SELECT e.* FROM entries e", []
    where = []
    if q:
        match = fts_query(q)
        if match:
            sql += " JOIN entries_fts f ON f.id = e.id"
            where.append("entries_fts MATCH ?")
            args.append(match)
    if status:
        where.append("e.status = ?")
        args.append(status)
    if kind:
        where.append("e.kind = ?")
        args.append(kind)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY COALESCE(e.decided_at, e.recorded_at)"
    return [_row_to_entry(r) for r in con.execute(sql, args).fetchall()]


def set_status(con: sqlite3.Connection, entry_id: str, status: str, trust: str | None = None,
               superseded_by: str | None = None) -> Entry:
    con.execute("UPDATE entries SET status = ?, trust = COALESCE(?, trust), superseded_by = COALESCE(?, superseded_by) WHERE id = ?",
                (status, trust, superseded_by, entry_id))
    con.commit()
    e = get_entry(con, entry_id)
    if e is None:
        raise KeyError(entry_id)
    return e


_STOP = set("""a an and are as at be but by for from has have i if in into is it its let lets me my not of on or our
so that the their them then there these this to us was we were what when which will with you your should would could
can do does just use using going go ok okay yes no maybe also than""".split())


def keywords(text: str, limit: int = 12) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9_\-]{2,}", text.lower())
    out: list[str] = []
    for w in words:
        if w not in _STOP and w not in out:
            out.append(w)
    return out[:limit]


def fts_query(text: str) -> str:
    kws = keywords(text)
    return " OR ".join(f'"{k}"' for k in kws)


# ---- feedback & runs --------------------------------------------------------

def add_feedback(con: sqlite3.Connection, target: str, action: str, entry_id: str | None = None,
                 note: str | None = None, snippet: str | None = None) -> None:
    con.execute("INSERT INTO feedback(id,entry_id,target,action,note,snippet,created_at) VALUES (?,?,?,?,?,?,?)",
                (new_id("f"), entry_id, target, action, note, snippet, now()))
    con.commit()


def feedback_rows(con: sqlite3.Connection, target: str, limit: int = 50) -> list[sqlite3.Row]:
    return con.execute("SELECT * FROM feedback WHERE target = ? ORDER BY created_at DESC LIMIT ?",
                       (target, limit)).fetchall()


def start_run(con: sqlite3.Connection, kind: str) -> str:
    rid = new_id("r")
    n = con.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
    con.execute("INSERT INTO runs(id,kind,started_at,feedback_count) VALUES (?,?,?,?)", (rid, kind, now(), n))
    con.commit()
    return rid


# ---- activity feed (what the watcher did) ---------------------------------

def add_activity(con: sqlite3.Connection, kind: str, title: str, detail: dict | None = None) -> None:
    con.execute("INSERT INTO activity(ts,kind,title,detail) VALUES (?,?,?,?)",
                (now(), kind, title, json.dumps(detail or {})))
    con.commit()


def recent_activity(con: sqlite3.Connection, limit: int = 30) -> list[dict]:
    rows = con.execute("SELECT id, ts, kind, title, detail FROM activity ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [{"id": r["id"], "ts": r["ts"], "kind": r["kind"], "title": r["title"], "detail": json.loads(r["detail"] or "{}")}
            for r in rows]
