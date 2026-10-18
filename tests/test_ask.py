from sthira import ask, sarvam


def test_record_intent():
    assert ask.record_intent("Record that we use SQLite for search") == "we use SQLite for search"
    assert ask.record_intent("We decided to use MongoDB.") == "We decided to use MongoDB"
    assert ask.record_intent("Why did we pick Postgres?") is None


def test_normalize_lang_and_disabled(monkeypatch):
    assert sarvam.normalize_lang("xx-XX") == "en-IN"
    assert sarvam.normalize_lang("kn-IN") == "kn-IN"
    monkeypatch.delenv("SARVAM_API_KEY", raising=False)
    assert not sarvam.enabled()
    try:
        sarvam.tts("hi")
    except sarvam.SarvamError:
        pass
    else:
        raise AssertionError("expected SarvamError")


def test_ask_drops_invented_citations(monkeypatch):
    from sthira import store
    from sthira.models import Entry, SourceRef
    con = store.connect(":memory:")
    e = Entry(id="e1", kind="decision", title="DB", statement="Acme uses Postgres", status="settled", trust="confirmed",
              recorded_at=store.now(), source=SourceRef(id="s", type="chat", title="chat", quote="we use postgres"))
    store.insert_entry(con, e)
    monkeypatch.setattr(ask.llm, "chat_json", lambda *a, **k: {"answer": "Postgres.", "cited": [0, 7, -1]})
    out = ask.ask(con, "which database do we use?")
    assert [c.id for c in out["citations"]] == ["e1"] and out["grounded"]
