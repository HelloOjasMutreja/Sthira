"""Sthira web demo: FastAPI over `sthira.api`, plus a single-page UI."""

from __future__ import annotations

import copy
import json
import os
import re
import queue
import threading
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from pydantic import BaseModel

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

# On serverless hosts only /tmp is writable; each cold start gets a freshly seeded demo ledger.
if "STHIRA_DB" not in os.environ:
    os.environ["STHIRA_DB"] = "/tmp/sthira.db" if os.environ.get("VERCEL") else str(ROOT / ".sthira" / "web.db")
# Values pasted into a dashboard often end with a newline, which makes the Authorization header invalid.
for _name in ("STHIRA_PROVIDER", "STHIRA_MODEL", "STHIRA_FALLBACK_MODEL", "STHIRA_OPENAI_BASE_URL", "STHIRA_OPENAI_API_KEY"):
    if os.environ.get(_name):
        os.environ[_name] = os.environ[_name].strip()
if os.environ.get("VERCEL") and "STHIRA_PROVIDER" not in os.environ:
    os.environ["STHIRA_PROVIDER"] = "openai"
    os.environ.setdefault("STHIRA_MODEL", "alibaba/qwen-3-32b")

from sthira import api, ask as ask_mod, config, llm, sarvam, store  # noqa: E402

from . import fallback, seed  # noqa: E402

app = FastAPI(title="Sthira", version="0.1.0")

# Provider errors can echo request headers (e.g. httpx's "Illegal header value b'Bearer ...'"), and these
# messages are returned to the browser. Never let a key out.
_SECRET = re.compile(r"(Bearer\s+)[^\s'\"]+|\b(?:gsk|sk|sk-proj|vck)[_-][A-Za-z0-9_-]{8,}", re.I)


def _safe(e: Exception) -> str:
    return _SECRET.sub(lambda m: (m.group(1) or "") + "[redacted]", str(e))


_lock = threading.Lock()


@app.middleware("http")
async def vercel_oidc(request, call_next):
    # Vercel passes a short-lived OIDC token per request; AI Gateway accepts it as the API key.
    token = request.headers.get("x-vercel-oidc-token")
    if token:
        os.environ["VERCEL_OIDC_TOKEN"] = token
    return await call_next(request)


def con():
    c = store.connect()
    seedable = not os.environ.get("STHIRA_NO_SEED") and (ROOT / "demo" / "seed.json").exists()
    if seedable and c.execute("SELECT COUNT(*) FROM entries").fetchone()[0] == 0:
        with _lock:
            if c.execute("SELECT COUNT(*) FROM entries").fetchone()[0] == 0:
                seed.load(c, ROOT / "demo" / "seed.json")
    return c


class ReviewBody(BaseModel):
    action: str
    note: str | None = None


class CheckBody(BaseModel):
    text: str


class CorrectBody(BaseModel):
    text: str
    note: str


class ExtractBody(BaseModel):
    limit: int | None = 3


@app.get("/", response_class=HTMLResponse)
def index():
    return (HERE / "static" / "index.html").read_text(encoding="utf-8")


@app.get("/api/meta")
def meta():
    return {"model": config.model(), "provider": config.provider(), "version": "0.1.0",
            "demo_drop": bool(os.environ.get("STHIRA_DEMO_DROP")),
            "voice": sarvam.enabled(), "languages": sarvam.LANGS}


@app.get("/api/entries")
def entries(status: str | None = None, kind: str | None = None, q: str | None = None):
    return [e.model_dump() for e in api.list_entries(status, kind, q, con=con())]


@app.get("/api/entries/{entry_id}/context")
def entry_context(entry_id: str, around: int = Query(2, ge=0, le=5)):
    """The source conversation around an entry's quote, so a decision can be read where it was made."""
    c = con()
    e = store.get_entry(c, entry_id)
    if e is None:
        raise HTTPException(404, "entry not found")
    conv_id, _, msg_id = e.source.locator.partition(" / ")
    rows = c.execute("SELECT msg_id, role, ts, text FROM messages WHERE source_id = ? AND conv_id = ? "
                     "ORDER BY COALESCE(ts, ''), rowid", (e.source.id, conv_id)).fetchall()
    idx = next((i for i, r in enumerate(rows) if r["msg_id"] == msg_id), None)
    if idx is None:
        return {"title": e.source.title, "messages": []}
    window = rows[max(0, idx - around): idx + around + 1]
    return {"title": e.source.title, "messages": [
        {"role": r["role"], "ts": r["ts"], "text": (r["text"] or "")[:1500], "match": r["msg_id"] == msg_id}
        for r in window]}


@app.post("/api/entries/{entry_id}/review")
def review(entry_id: str, body: ReviewBody):
    try:
        return api.review(entry_id, body.action, body.note, con=con()).model_dump()
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e))


class ReplaceBody(BaseModel):
    statement: str
    rationale: str = ""


@app.post("/api/entries/{old_id}/replace")
def replace(old_id: str, body: ReplaceBody):
    try:
        r = api.replace(old_id, body.statement[:1000], body.rationale[:1000], con=con())
    except KeyError:
        raise HTTPException(404, "entry not found")
    return {"old": r["old"].model_dump(), "new": r["new"].model_dump()}


@app.post("/api/entries/{old_id}/supersede/{new_id}")
def supersede(old_id: str, new_id: str):
    try:
        return api.supersede(old_id, new_id, con=con()).model_dump()
    except KeyError as e:
        raise HTTPException(404, f"entry not found: {e}")
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/check")
def check(body: CheckBody):
    if not body.text.strip():
        raise HTTPException(400, "text is empty")
    text = body.text[:4000]
    c = con()
    key = (fallback.normalize(text), _ledger_fingerprint(c))
    hit = _verdict_cache.get(key)
    if hit and time.monotonic() - hit[0] < VERDICT_TTL:
        return {**copy.deepcopy(hit[1]), "cached": True}
    try:
        v = api.check(text, con=c).model_dump()
    except Exception as e:
        # If the hosted model is unreachable: the built-in examples fall back to verdicts recorded from a
        # real local Qwen3 run, and other text to a keyword match on explicitly rejected alternatives.
        # Both are labelled as such. If neither applies, surface the error honestly.
        cached = _cached_checks().get(fallback.normalize(text))
        if cached:
            cached["model"] = f"{cached['model']} (recorded from a local run; hosted model unavailable)"
            return {**cached, "fallback": "recorded"}
        v = fallback.keyword_check(text, api.list_entries("settled", con=con()))
        if v:
            return {**v.model_dump(), "fallback": "keyword"}
        raise HTTPException(502, f"Model call failed: {_safe(e)}")
    # Only real model verdicts are cached; the fallbacks above return before reaching here.
    _verdict_cache.pop(key, None)
    if len(_verdict_cache) >= VERDICT_CACHE_MAX:
        _verdict_cache.pop(next(iter(_verdict_cache)))
    _verdict_cache[key] = (time.monotonic(), copy.deepcopy(v))
    return v


# Repeated checks of the same text (e.g. judges clicking the same example) reuse the model's verdict instead of
# spending the hosted model's small per-minute quota. The key includes a fingerprint of the settled ledger and of
# the feedback, so a correction or a new or changed decision makes the next check ask the model again.
VERDICT_TTL = 600
VERDICT_CACHE_MAX = 256
_verdict_cache: dict[tuple, tuple[float, dict]] = {}


def _ledger_fingerprint(c) -> tuple:
    settled = c.execute("SELECT COUNT(*), MAX(recorded_at) FROM entries WHERE status = 'settled'").fetchone()
    feedback = c.execute("SELECT COUNT(*) FROM feedback").fetchone()
    return (settled[0], settled[1], feedback[0])


def _cached_checks() -> dict:
    import json

    p = ROOT / "demo" / "cached_checks.json"
    data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    return {fallback.normalize(k): v for k, v in data.items()}


@app.post("/api/correct")
def correct(body: CorrectBody):
    api.correct_check(body.text, body.note, con=con())
    return {"ok": True}


@app.post("/api/ingest")
async def ingest(file: UploadFile = File(...), kind: str | None = Form(None)):
    data = await file.read()
    if len(data) > 4_000_000:
        raise HTTPException(413, "File too large for the hosted demo (4 MB). Run Sthira locally for full exports.")
    return api.ingest_upload(file.filename or "upload.json", data, kind or None, con=con())


def _seconds_per_chunk_hint() -> float:
    """A first guess for the ETA before any chunk has finished: a hosted model is quick, a laptop CPU is not."""
    return 4.0 if config.provider() == "openai" else 25.0


@app.post("/api/import/stream")
async def import_stream(file: UploadFile = File(...), kind: str | None = Form(None)):
    """Import and extract, reporting progress as it happens (newline-delimited JSON), so the UI can show real
    progress and an honest ETA instead of a spinner. One request, one worker thread, so it behaves the same on
    serverless hosts where each instance has its own /tmp."""
    data = await file.read()
    if len(data) > 4_000_000:
        raise HTTPException(413, "File too large for the hosted demo (4 MB). Run Sthira locally for full exports.")
    name = file.filename or "upload.json"
    q: queue.Queue = queue.Queue()
    limit = 3 if os.environ.get("VERCEL") else None  # the hosted demo reads at most 3 conversations

    def worker():
        t0 = time.time()
        try:
            c = con()
            r = api.ingest_upload(name, data, kind or None, con=c)
            q.put({"event": "parsed", "messages": r["messages"], "sources": r["sources"],
                   "seconds_per_chunk_hint": _seconds_per_chunk_hint(), "model": config.model()})
            skipped: list[str] = []
            entries = api.extract(limit, con=c, source_ids=r["source_ids"], errors=skipped,
                                  on_chunk=lambda ev: q.put({"event": "chunk", **ev}))
            q.put({"event": "done", "entries": [e.model_dump() for e in entries], "skipped": len(skipped),
                   "elapsed": round(time.time() - t0, 1)})
        except Exception as e:  # surface it to the UI instead of a dropped connection
            q.put({"event": "error", "message": f"{type(e).__name__}: {e}"[:300]})
        finally:
            q.put(None)

    threading.Thread(target=worker, daemon=True, name="sthira-import").start()

    def stream():
        while True:
            item = q.get()
            if item is None:
                return
            yield json.dumps(item) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/import")
async def import_and_extract(file: UploadFile = File(...), kind: str | None = Form(None)):
    """Ingest + extract in one request (serverless instances don't share /tmp between requests)."""
    data = await file.read()
    if len(data) > 4_000_000:
        raise HTTPException(413, "File too large for the hosted demo (4 MB). Run Sthira locally for full exports.")
    c = con()
    r = api.ingest_upload(file.filename or "upload.json", data, kind or None, con=c)
    try:
        llm.chat_json("Reply with JSON.", 'Return {"ok": true}', {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]})
    except Exception as e:
        raise HTTPException(502, f"Model call failed: {_safe(e)}")
    entries = api.extract(3, con=c, source_ids=r["source_ids"])  # only this upload, never someone else's
    return {"messages": r["messages"], "sources": r["sources"], "entries": [e.model_dump() for e in entries]}


@app.get("/api/health")
def health():
    try:
        out = llm.chat_json("Reply with JSON.", 'Return {"ok": true}', {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]})
        return {"model": config.model(), "ok": bool(out.get("ok"))}
    except Exception as e:
        raise HTTPException(502, f"Model call failed: {_safe(e)}")


@app.post("/api/extract")
def extract(body: ExtractBody):
    try:
        return [e.model_dump() for e in api.extract(min(body.limit or 3, 5), con=con())]
    except Exception as e:
        raise HTTPException(502, f"Model call failed: {_safe(e)}")


@app.post("/api/demo/drop")
def demo_drop():
    """Demo mode only: put a realistic Claude Code session (the agent proposes going against two decisions) in the
    inbox folder, exactly as a real session would appear, so the watcher can be seen reacting to it."""
    if not os.environ.get("STHIRA_DEMO_DROP"):
        raise HTTPException(404, "not available")
    import shutil
    import time as _t

    src = ROOT / "demo" / "claude_code" / "session.jsonl"
    from sthira import watch as _watch

    inbox = _watch.inbox_dir()
    dest = inbox / f"acme-session-{int(_t.time())}.jsonl"
    shutil.copyfile(src, dest)
    return {"dropped": dest.name}


@app.get("/api/demo-session")
def demo_session():
    """The demo Claude Code session, for the in-browser agent replay. Works on any host: the browser types it out and
    calls /api/check on each agent message, so it needs neither demo mode nor the background watcher."""
    from sthira.ingest import claude_code

    path = ROOT / "demo" / "claude_code" / "session.jsonl"
    if not path.exists():
        return {"title": "", "messages": []}
    title, msgs = claude_code.parse(path.read_text(encoding="utf-8"), path.name)
    return {"title": title, "messages": [{"role": m.role, "text": m.text} for m in msgs]}


@app.get("/api/activity")
def activity(limit: int = 30):
    """What the background watcher has done: files read, entries waiting, agents caught going against decisions."""
    return api.recent_activity(min(max(limit, 1), 100), con=con())


@app.post("/api/activity/seen")
def activity_seen():
    api.mark_activity_seen(con=con())
    return {"ok": True}


@app.get("/api/rules")
def rules():
    return api.learned_rules(con=con())


@app.get("/api/stats")
def stats():
    return api.feedback_stats(con=con())


@app.get("/api/agents-md")
def agents_md():
    from sthira import sync

    return {"markdown": sync.render(con())}


# ---- voice talkback (Sarvam): speak, ask your ledger, hear the answer --------------------------------------------
_voice_hits: dict[str, list[float]] = {}


def _voice_guard(request: Request):
    """The hosted demo spends a shared Sarvam budget: allow ~20 voice calls a minute per visitor."""
    if not sarvam.enabled():
        raise HTTPException(503, "Voice is not configured on this server.")
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "")).split(",")[0].strip()
    now = time.time()
    hits = [t for t in _voice_hits.get(ip, []) if now - t < 60]
    if len(hits) >= 20:
        raise HTTPException(429, "Too many voice requests, give it a minute.")
    _voice_hits[ip] = hits + [now]


class AskBody(BaseModel):
    text: str
    lang: str = "en-IN"


class SpeakBody(BaseModel):
    text: str
    lang: str = "en-IN"


def _cite(e) -> dict:
    return {"id": e.id, "title": e.title, "statement": e.statement, "status": e.status, "decided_at": e.decided_at,
            "source": e.source.title, "quote": e.source.quote}


@app.post("/api/voice/stt")
async def voice_stt(request: Request, audio: UploadFile = File(...)):
    _voice_guard(request)
    data = await audio.read()
    if not data or len(data) > 8_000_000:
        raise HTTPException(400, "No audio, or too long (keep it under a minute).")
    try:
        return sarvam.stt(data, audio.filename or "speech.webm", audio.content_type or "audio/webm")
    except sarvam.SarvamError as e:
        raise HTTPException(502, str(e))


@app.post("/api/voice/tts")
def voice_tts(body: SpeakBody, request: Request):
    _voice_guard(request)
    try:
        return Response(sarvam.tts(body.text, body.lang), media_type="audio/wav")
    except sarvam.SarvamError as e:
        raise HTTPException(502, str(e))


@app.post("/api/ask")
def ask_ledger(body: AskBody, request: Request):
    """Answer a question from the ledger, or (if it sounds like a decision) check it and record it. Any Indian language:
    the question is translated to English for the grounded answer, which is translated back."""
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "Ask something.")
    lang = sarvam.normalize_lang(body.lang)
    foreign = lang != "en-IN"
    if foreign:
        _voice_guard(request)  # translation uses Sarvam
    try:
        english = sarvam.translate(text, "en-IN", lang) if foreign else text
        decision = ask_mod.record_intent(english)
        c = con()
        if decision:
            v = api.check(decision, con=c)
            api.propose(decision, source_title="Spoken in Sthira", con=c)
            if v.verdict in ("contradicts", "supersedes") and v.conflicts:
                top = v.conflicts[0]
                reply = (f"Careful. That goes against a decision you made: {top.entry.statement} {top.explanation} "
                         "I noted it as proposed, not settled.")
            else:
                reply = "Noted. It doesn't conflict with anything settled, and I recorded it as proposed for you to confirm."
            cites = [_cite(x.entry) for x in v.conflicts]
            grounded = bool(cites)
        else:
            out = ask_mod.ask(c, english)
            reply, cites, grounded = out["answer"], [_cite(e) for e in out["citations"]], out["grounded"]
        spoken = sarvam.translate(reply, lang, "en-IN") if foreign else reply
    except sarvam.SarvamError as e:
        raise HTTPException(502, str(e))
    except Exception as e:
        raise HTTPException(502, f"Model call failed: {_safe(e)}")
    return {"question": text, "question_en": english, "answer": spoken, "answer_en": reply, "lang": lang,
            "citations": cites, "grounded": grounded, "recorded": bool(decision)}
