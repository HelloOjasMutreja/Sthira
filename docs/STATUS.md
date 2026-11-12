# Live status board

Update this file whenever you finish something, get blocked, or hand off (for example near a usage limit). Newest first.

## 13 Nov 2026: rebrand, on branch `feat/brand-strata` (not merged, not deployed)

- **What:** the web and desktop UI is restyled as "settled strata" (see `docs/BRAND.md`). Only `web/static/index.html` changed in behaviour: new stylesheet, the strata canvas in the hero, a new mark and footer. Every element id and flow is unchanged.
- **Checked:** 77 tests pass. In Chromium at 1440, 820 and 375px: no console errors, no horizontal overflow, 60 fps. Check, keep, change-my-mind, replay, drawer, palette and tour all run.
- **Open:** the hosted Groq key has expired (401), so both live sites answer from recorded verdicts and "Ask your ledger" fails until a new key is set. The mic was still never tested in a browser.
- **Next:** a human opens the PR; Vidit owns `web/`, so he should review it.

## Board

**⏰ First-round evaluation runs 14:00–15:30 (be demo-ready by 14:00).** Criteria: one working feature · relevance to the theme · clear problem and solution. Submit: repo URL + Track 2 / O2 (portal TBA).

**Live demo:** https://sthira-mocha.vercel.app · **PRs:** #1 core → #2 demo/eval → #3 web (stacked; merge in order)

| Workstream | Owner | Status | Next step |
|---|---|---|---|
| Core + demo/eval (#1, #2) | Claude | done, CI green | merge at ~12:00 |
| Cursor rules #10 · model-down errors #11 · .vtt/.srt #12 · Gemini #13 · learned rules #14 · review fixes #15 | Claude | done, stacked on #2 | merge in order after #2 (integration dry-run: all merge cleanly, 17+ tests pass) |
| Web demo (#3) | Claude + Vidit (#9 merged) | **live**: learned-rules panel, labelled offline fallbacks, scoped import | merge last |
| Dogfood: Sthira on our own build session | Claude | running (qwen3:4b) | package as a demo moment |
| **Hosted model** | **Ojas** | blocked | Vercel card **or** Groq key in project env |
| **ShipWright app** | **Ojas** | not installed | install now if we want leaderboard credit before the merges |
| **Collaborators: Vidit, Danica** | **Ojas** | todo | fork PRs miss ShipWright's full review |
| Demo rehearsal / backup video / submission / X post | Danica | todo | `docs/DEMO_SCRIPT.md`, `docs/SUBMISSION.md` |

## Keys and secrets (names only, never values here)

| What | Where it lives | Used for |
|---|---|---|
| Groq key (free tier, expires about 25 Oct 2026) | Vercel project *sthira* → Production env `STHIRA_OPENAI_API_KEY`; Ojas's local, gitignored `.env` | the live demo's open-weight model |
| `STHIRA_PROVIDER=openai`, `STHIRA_OPENAI_BASE_URL`, `STHIRA_MODEL=qwen/qwen3.8-27b`, `STHIRA_FALLBACK_MODEL=openai/gpt-oss-120b` | same Vercel env | model routing (fallback kicks in when Groq's 8k tokens/min quota is hit) |
| Anthropic key (**paid**) | Ojas's local `.env` only. **Not deployed, not in Vercel.** | nothing yet; local testing only, ask Ojas first |

- Never paste keys into PRs, issues or chat logs. Both keys were shared in a chat, so **rotate or revoke them after the event**.
- Vidit: to run the web app locally against the hosted model, copy `.env.example`, ask Ojas for the key privately, and `export` the variables.
- Groq's free tier is about 8,000 tokens a minute per model, so the live site can answer roughly 4 to 6 checks a minute. Past that it falls back to the second model, then to the labelled offline fallbacks.

## Demo data brief (Danica)

Create these in `demo/` (fictional project "Acme Notes", a note-taking app):

1. `demo/chatgpt/conversations.json`: 3 to 4 short conversations in ChatGPT export format (Claude can give you the schema). Plant these:
   - **Decision (4 Mar 2026):** use Postgres, not MongoDB, because we need joins across users and orgs.
   - **Decision:** auth with magic links, no passwords.
   - **Open question:** pricing, monthly vs annual (never resolved).
   - Plenty of normal chatter that is **not** a decision.
2. `demo/meetings/2026-05-12-standup.md`: a short transcript with one decision (ship mobile after web) and one commitment ("Danica will draft the onboarding copy by Friday").
3. `demo/claude_code/session.jsonl`: a short coding session (Claude can generate it in the right format) where the agent **proposes switching the user store to MongoDB**. This is the contradiction for the demo.
4. `eval/gold.json`: the list of real decisions, questions and commitments you planted, so we can measure precision and recall.

## Log
- 11:35: Hosted model live (Groq, qwen3.8-27b + gpt-oss-120b fallback): checks ~1 s, upload+extract ~2 s. Production was down about 5 min at 11:30 because I deployed a half-merged tree (fixed; deploys now gated on tests).
- 11:10: Added #10–#15 (Cursor rules, model-down errors, subtitles, Gemini, learned rules, Vidit's review fixes). Learned-rules panel live. Integration dry-run clean. Dogfood found real decisions from our own session.
- 10:55: Merged Vidit's #9 (labelled keyword fallback for typed checks) and redeployed. Handbook update: first-round eval 14:00–15:30, criteria published, live URL no longer required (we have one anyway). Primer PDF in docs/primer/.
- Vidit: when the hosted model is down, typed checks now fall back to a labelled keyword match on explicitly rejected alternatives (e.g. "MongoDB"), and the recorded examples match regardless of case and spacing. Upload/review/teach errors are shown in the UI. Branch `feat/web-model-errors` (PR on top of #3).
- 10:05: Critic pass added (checks 6/6). qwen3:8b comparison done. Live site deployed with seeded ledger and labelled fallback. Waiting on two Ojas-only actions (hosted model, ShipWright).
- 09:27: `sthira demo` proves learning: precision 0.40 → 0.57 (run 1), and both agent contradictions in today's Claude Code session are caught. Web demo works locally. PR #1 is open (no ShipWright review yet, so the app may need installing by Ojas).
- 09:15: Core engine works end to end on qwen3:4b: ingest, extract (~50s for 2 convs), settle/reject, cited contradiction check (~15s), sync, MCP. 6 tests pass. `sthira.api` matches CONTRACTS.md, so Vidit can import it directly in `web/`.
- 08:21: Repo cloned and empty. Plan written (`docs/PLAN.md`). Local Ollama has qwen3:4b, qwen3:8b and nomic-embed-text.
