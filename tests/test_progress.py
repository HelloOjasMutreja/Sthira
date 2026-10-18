from sthira import api, llm, store

ENTRY = {"kind": "decision", "title": "Use SQLite", "statement": "Use SQLite for search.", "rationale": "small team",
         "alternatives_rejected": [], "quote": "we use SQLite for search", "msg": 0, "confidence": 0.9}


def test_on_chunk_reports_start_then_each_chunk_with_what_it_found(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: {"entries": [ENTRY]})
    con = store.connect(tmp_path / "t.db")
    api.ingest_upload("2026-10-18-plan.md", b"Ojas: we use SQLite for search.\n", con=con)
    events = []
    api.extract(con=con, on_chunk=events.append)
    assert events[0] == {"phase": "start", "total": 1, "conversations": 1, "messages": 1}
    read = events[-1]
    assert read["phase"] == "read" and read["done"] == 1 and read["total"] == 1
    assert read["found"][0]["statement"] == "Use SQLite for search." and read["found"][0]["quote"]


def test_split_chunks_raise_the_total_and_progress_still_finishes(tmp_path, monkeypatch):
    def fake(system, user, schema, **k):
        if user.count("\n[") > 1:
            raise llm.LLMError("Failed to validate JSON")
        return {"entries": []}

    monkeypatch.setattr(llm, "chat_json", fake)
    con = store.connect(tmp_path / "t.db")
    api.ingest_upload("2026-10-18-plan.md", b"Ojas: one.\nDanica: two.\n", con=con)
    events = []
    api.extract(con=con, on_chunk=events.append)
    assert any(e["phase"] == "split" for e in events)
    last = events[-1]
    assert last["done"] == last["total"] == 2  # 1 chunk became 2, and both were read


def test_unreadable_chunk_is_reported_as_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: (_ for _ in ()).throw(llm.LLMError("nope")))
    con = store.connect(tmp_path / "t.db")
    api.ingest_upload("2026-10-18-plan.md", b"Ojas: one.\n", con=con)
    events = []
    api.extract(con=con, on_chunk=events.append)
    assert events[-1]["phase"] == "skip" and events[-1]["done"] == 1 and "nope" in events[-1]["error"]
