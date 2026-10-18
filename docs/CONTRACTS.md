# Interfaces (code against these so work can run in parallel)

If you need to change anything here, tell the team and update this file in the same PR.

## Entry (the ledger row)

```json
{
  "id": "e_01H...",
  "kind": "decision | open_question | preference | commitment | lesson | assumption",
  "title": "Use Postgres for the user store",
  "statement": "We will use Postgres, not MongoDB, for the user store.",
  "rationale": "We need relational joins across users and orgs.",
  "alternatives_rejected": ["MongoDB"],
  "project": "acme-app",
  "status": "proposed | settled | rejected | superseded",
  "trust": "confirmed | quarantined",
  "superseded_by": null,
  "decided_at": "2026-03-04T10:12:00Z",
  "recorded_at": "2026-10-18T09:40:00Z",
  "source": {
    "id": "s_...",
    "type": "chatgpt | claude_code | transcript",
    "title": "DB choice",
    "locator": "conversation <id> / message <id>",
    "quote": "ok let's go with postgres, we need joins"
  },
  "confidence": 0.82
}
```

## Check verdict

```json
{
  "input": "Let's switch the user store to MongoDB",
  "verdict": "contradicts | consistent | unrelated | supersedes",
  "conflicts": [ { "entry": "<Entry>", "explanation": "…" } ],
  "model": "qwen3:4b"
}
```

## Python API (`sthira.api`, stable for the web and MCP layers)

```python
from sthira import api
api.ingest(path: str, kind: str | None = None) -> dict          # {"messages": n, "sources": n}
api.extract(limit: int | None = None) -> list[Entry]            # new proposed entries
api.list_entries(status: str | None = None, kind: str | None = None, q: str | None = None) -> list[Entry]
api.review(entry_id: str, action: "settle" | "reject", note: str | None = None) -> Entry
api.supersede(old_id: str, new_id: str) -> Entry
api.check(text: str) -> Verdict
api.feedback_stats() -> dict                                    # {"corrections": n, "precision_before": x, "precision_after": y}
api.sync(path: str = "AGENTS.md") -> str                        # returns the written block
```

## HTTP API (`web/`, FastAPI, mirrors the Python API)

| Method | Path | Body / query | Returns |
|---|---|---|---|
| GET | `/api/entries` | `status, kind, q` | `Entry[]` |
| GET | `/api/entries/{id}/context` | `around` (default 2, clamped 0 to 5) | `{title, messages: [{role, ts, text, match}]}`: the source conversation around the entry's quote. `source.locator` is split on `" / "` into conv_id and msg_id; up to `around` stored messages either side of the quoted one, ordered by `COALESCE(ts, '')` then rowid, with `match: true` on the quoted message and each `text` cut to 1500 characters. 404 for an unknown entry; empty `messages` if the message is not stored |
| POST | `/api/entries/{id}/review` | `{action, note}` | `Entry` |
| POST | `/api/check` | `{text}` | `Verdict`, plus `"cached": true` when an identical check against the same settled ledger and feedback ran in the last 10 minutes (fallback verdicts are never cached) |
| POST | `/api/ingest` | multipart file + `kind` | `{messages, sources}` |
| POST | `/api/extract` | `{limit}` | `Entry[]` |
| GET | `/api/stats` | none | feedback stats + counts |
| GET | `/api/eval` | none | `{source, url, date, setup, extraction: {headline, what, rows: [{model, run, before, after, recall, caught, drifts, headline?}]}, checks: {model, cases, rows: [{pipeline, correct, total, latency, note, winner?}], critic}, dogfood: {what, messages, entries, model, right: [str], wrong: [str], bug}, limits: [str]}`: the offline evaluation's headline numbers, a static file (`web/eval_summary.json`) transcribed from `eval/README.md`. Not computed from the ledger; `/api/stats` is the live one |
| GET | `/api/demo-session` | none | `{title, messages: [{role, text}]}`: the demo Claude Code session (`demo/claude_code/session.jsonl`) parsed with `sthira.ingest.claude_code.parse`, for the in-browser agent replay; empty `messages` if the file is missing |

## Environment

| Var | Default | Meaning |
|---|---|---|
| `STHIRA_DB` | `~/.sthira/sthira.db` | SQLite file |
| `STHIRA_PROVIDER` | `ollama` | `ollama` or `openai` (any OpenAI-compatible endpoint serving an open-weight model) |
| `STHIRA_MODEL` | `qwen3:4b` | model name for the provider |
| `OLLAMA_HOST` | `http://localhost:11434` | |
| `STHIRA_OPENAI_BASE_URL` / `STHIRA_OPENAI_API_KEY` | none | hosted open-weight endpoint for the live demo |
