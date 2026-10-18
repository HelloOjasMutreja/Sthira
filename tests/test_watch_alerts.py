import json
import os
import time

from sthira import llm, store, watch
from sthira.models import Entry, SourceRef


def _settled(con, statement, alts=()):
    return store.insert_entry(con, Entry(
        id=store.new_id("e"), kind="decision", title=statement[:20], statement=statement, status="settled", trust="confirmed",
        alternatives_rejected=list(alts), decided_at="2026-03-04T00:00:00Z", recorded_at=store.now(),
        source=SourceRef(id="s", type="chatgpt", title="DB choice", quote="we go with Postgres, not MongoDB")))


def _session(path, assistant_text):
    lines = [
        {"type": "user", "sessionId": "s1", "uuid": "u1", "timestamp": "2026-10-18T09:00:00Z",
         "message": {"role": "user", "content": "The notes search is slow, can you fix the user store performance?"}},
        {"type": "assistant", "sessionId": "s1", "uuid": "u2", "timestamp": "2026-10-18T09:01:00Z",
         "message": {"role": "assistant", "content": [{"type": "text", "text": assistant_text}]}},
    ]
    _write(path, "\n".join(json.dumps(x) for x in lines) + "\n")


def _write(path, text):
    path.write_text(text, encoding="utf-8")
    t = time.time() - 60
    os.utime(path, (t, t))


def _fake_llm(system, user, schema, **k):
    if "protect a person's settled decisions" in system:  # the contradiction check
        return {"verdict": "contradicts", "conflicts": [{"n": 0, "explanation": "MongoDB was rejected."}]}
    if "double-check" in system:  # the critic
        return {"what_settled_chose": "Postgres", "what_new_work_does": "MongoDB", "goes_against_settled": True}
    return {"entries": []}


def test_agent_going_against_a_decision_raises_an_alert(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "chat_json", _fake_llm)
    con = store.connect(tmp_path / "t.db")
    _settled(con, "Use Postgres for the user store.", ["MongoDB"])
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    _session(inbox / "session.jsonl",
             "I looked at the queries. The plan is to migrate the user store from Postgres to MongoDB to avoid joins.")
    events = watch.scan_once(con, [inbox])
    assert events[0].alerts == 1
    feed = store.recent_activity(con)
    kinds = [a["kind"] for a in feed]
    assert "alert" in kinds and "read" in kinds
    alert = next(a for a in feed if a["kind"] == "alert")
    assert alert["detail"]["decision"] == "Use Postgres for the user store."
    assert "MongoDB" in alert["detail"]["agent_said"] and alert["detail"]["quote"]


def test_no_alert_without_settled_decisions(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "chat_json", _fake_llm)
    con = store.connect(tmp_path / "t.db")
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    _session(inbox / "session.jsonl", "migrating everything to MongoDB right now. " * 3)
    watch.scan_once(con, [inbox])
    assert [a["kind"] for a in store.recent_activity(con)] == ["read"]


def test_error_is_recorded_in_the_feed(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "chat_json", _fake_llm)
    con = store.connect(tmp_path / "t.db")
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    _write(inbox / "broken.zip", "not a zip")
    watch.scan_once(con, [inbox])
    feed = store.recent_activity(con)
    assert feed[0]["kind"] == "error" and "broken.zip" in feed[0]["title"]
