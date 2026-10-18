import os
import time

from sthira import llm, store, watch

FAKE = {"entries": [{"kind": "decision", "title": "Use SQLite", "statement": "Use SQLite for search.", "rationale": "small team",
                     "alternatives_rejected": ["Elasticsearch"], "quote": "we use SQLite for search", "msg": 0, "confidence": 0.9}]}


def _write(path, text, age=60):
    path.write_text(text, encoding="utf-8")
    t = time.time() - age
    os.utime(path, (t, t))


def test_new_file_is_ingested_and_extracted(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: FAKE)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    _write(inbox / "2026-10-18-plan.md", "Ojas: we use SQLite for search.\n")
    con = store.connect(tmp_path / "t.db")
    events = watch.scan_once(con, [inbox])
    assert len(events) == 1 and events[0].messages == 1 and events[0].entries == 1
    assert [e.status for e in store.list_entries(con)] == ["proposed"]
    assert watch.scan_once(con, [inbox]) == []  # unchanged: nothing to do


def test_file_still_being_written_waits(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: FAKE)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    _write(inbox / "live.md", "Ojas: we use SQLite for search.\n", age=2)  # modified 2 s ago
    con = store.connect(tmp_path / "t.db")
    assert watch.scan_once(con, [inbox], settle=20) == []
    assert len(watch.scan_once(con, [inbox], settle=20, now=time.time() + 60)) == 1  # quiet now


def test_growing_session_only_sends_new_messages_plus_context(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(llm, "chat_json", lambda s, u, sc, **k: calls.append(u) or {"entries": []})
    d = tmp_path / "inbox"
    d.mkdir()
    f = d / "2026-10-18-standup.md"
    lines = [f"Ojas: line number {i}." for i in range(1, 7)]
    _write(f, "\n".join(lines) + "\n")
    con = store.connect(tmp_path / "t.db")
    assert watch.scan_once(con, [d])[0].messages == 6
    _write(f, "\n".join(lines + ["Danica: brand new line."]) + "\n")
    ev = watch.scan_once(con, [d])
    assert ev[0].messages == 1  # the six old messages are not re-added
    sent = calls[-1]
    assert "brand new line" in sent and "line number 5" in sent and "line number 6" in sent  # new + 2 context
    assert "line number 1" not in sent and "line number 4" not in sent  # the rest of the session is not re-sent


def test_first_run_without_backfill_only_marks_existing_files(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: FAKE)
    d = tmp_path / "history"
    d.mkdir()
    _write(d / "old.md", "Ojas: we use SQLite for search.\n")
    con = store.connect(tmp_path / "t.db")
    assert watch.scan_once(con, [d], first_run_backfill=False) == []
    assert store.list_entries(con) == []  # years of history are not read unasked
    _write(d / "old.md", "Ojas: we use SQLite for search.\nDanica: new line.\n")
    assert len(watch.scan_once(con, [d], first_run_backfill=False)) == 1  # but changes from now on are


def test_bad_file_does_not_stop_the_scan(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: FAKE)
    d = tmp_path / "inbox"
    d.mkdir()
    _write(d / "broken.zip", "not a zip at all")
    _write(d / "2026-10-18-ok.md", "Ojas: we use SQLite for search.\n")
    con = store.connect(tmp_path / "t.db")
    events = watch.scan_once(con, [d])
    assert any(e.error for e in events) and any(e.entries == 1 for e in events)


def test_file_dropped_after_an_empty_first_pass_is_not_skipped(tmp_path, monkeypatch):
    """Regression: 'first run' used to be inferred from an empty table, so with nothing in the folders at the first scan
    every later pass looked like a first run too and silently marked new files as seen."""
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: FAKE)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    con = store.connect(tmp_path / "t.db")
    assert watch.scan_once(con, [inbox], first_run_backfill=False) == []  # first pass: nothing there yet
    _write(inbox / "2026-10-18-plan.md", "Ojas: we use SQLite for search.\n")
    events = watch.scan_once(con, [inbox], first_run_backfill=False)
    assert len(events) == 1 and events[0].entries == 1


def test_inbox_only_mode_never_includes_claude_history(tmp_path, monkeypatch):
    monkeypatch.setenv("STHIRA_DB", str(tmp_path / "x.db"))
    assert watch.default_dirs(inbox_only=True) == [tmp_path / "inbox"]
