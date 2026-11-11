# Live status board

Update this file whenever you finish something, get blocked, or hand off (for example near a usage limit). Newest first.

## Board

**⏰ First-round evaluation runs 14:00–15:30 (be demo-ready by 14:00).** Criteria: one working feature · relevance to the theme · clear problem and solution. Submit: repo URL + Track 2 / O2 (portal TBA).

**Live demo:** https://sthira-mocha.vercel.app · **PRs:** #1 core → #2 demo/eval → #3 web (stacked; merge in order)

| Workstream | Owner | Status | Next step |
|---|---|---|---|
| **All code is on `main`** (PRs #1 to #3 and #9 to #17 merged 12:07) | Claude | done; fresh-clone check: 31 tests pass, CLI runs, CI green | keep `main` green: branch, PR, merge |
| Live demo https://sthira-mocha.vercel.app | Claude | deployed from `main` (hosted open-weight model via Groq) | none |
| PR #8 (Vidit's web scaffold) | Vidit | overlaps the merged web app | close it, or send a small follow-up PR for anything it adds |
| **ShipWright app** | **Ojas** | not installed, so merged PRs got no review | install it now; PRs opened **from now on** get reviewed and count on the leaderboard |
| **Rotate the Groq and Anthropic keys after the event** | **Ojas** | todo | both were shared in a chat |
| Collaborators: Vidit + Danica | **Ojas** | todo | Settings → Collaborators |
| Demo rehearsal / backup video / submission / X post | Danica | todo | `docs/DEMO_SCRIPT.md`, `docs/SUBMISSION.md`. **First-round evaluation 14:00 to 15:30.** |

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
- 12:08: Merged everything into `main` in dependency order (dry-run clean first), verified from a fresh clone, redeployed the live site from `main`. Stats: 31 tests, 7 CLI commands added since the plan, 5 input formats.
- 11:35: Hosted model live (Groq, qwen3.8-27b + gpt-oss-120b fallback): checks ~1 s, upload+extract ~2 s. Production was down about 5 min at 11:30 because I deployed a half-merged tree (fixed; deploys now gated on tests).
- 11:10: Added #10–#15 (Cursor rules, model-down errors, subtitles, Gemini, learned rules, Vidit's review fixes). Learned-rules panel live. Integration dry-run clean. Dogfood found real decisions from our own session.
- 10:55: Merged Vidit's #9 (labelled keyword fallback for typed checks) and redeployed. Handbook update: first-round eval 14:00–15:30, criteria published, live URL no longer required (we have one anyway). Primer PDF in docs/primer/.
- Vidit: when the hosted model is down, typed checks now fall back to a labelled keyword match on explicitly rejected alternatives (e.g. "MongoDB"), and the recorded examples match regardless of case and spacing. Upload/review/teach errors are shown in the UI. Branch `feat/web-model-errors` (PR on top of #3).
- 10:05: Critic pass added (checks 6/6). qwen3:8b comparison done. Live site deployed with seeded ledger and labelled fallback. Waiting on two Ojas-only actions (hosted model, ShipWright).
- 09:27: `sthira demo` proves learning: precision 0.40 → 0.57 (run 1), and both agent contradictions in today's Claude Code session are caught. Web demo works locally. PR #1 is open (no ShipWright review yet, so the app may need installing by Ojas).
- 09:15: Core engine works end to end on qwen3:4b: ingest, extract (~50s for 2 convs), settle/reject, cited contradiction check (~15s), sync, MCP. 6 tests pass. `sthira.api` matches CONTRACTS.md, so Vidit can import it directly in `web/`.
- 08:21: Repo cloned and empty. Plan written (`docs/PLAN.md`). Local Ollama has qwen3:4b, qwen3:8b and nomic-embed-text.
