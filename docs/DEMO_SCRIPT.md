# Demo script

Two versions: **A. the 2-minute run** for first-round evaluation (14:00 to 15:30), and **B. the 5-minute run** for the later judging rounds (15:45 to 17:30, criteria unpublished). Then a fallback table, the numbers you can say out loud, and likely questions.

**First round is judged on three things. Say each one out loud, in this order:**
1. *Clear problem and solution* (open with the problem before touching the screen).
2. *At least one working feature* (the live check and the desktop moment).
3. *Relevance to the theme* ("Track 2, problem statement O2: adaptive AI with memory and self-correction, on an open-weight model").

> The desktop app, redesign and reader live in PRs #22, #24, #27 and #28. The commands below need those merged (or the branch `feat/ui-reading-progress` checked out).

## Before the judges arrive (10 minutes)

| Do | How |
|---|---|
| Warm the local model | `ollama run qwen3:4b "hi"` once, then exit |
| Open the live site in a tab | https://sthira-mocha.vercel.app (check the model badge shows a model name) |
| Start the desktop demo (hosted model, fast) | `powershell -ExecutionPolicy Bypass -File scripts\launch-demo.ps1` |
| Same, but fully local (slower, the privacy proof) | add `-Local` |
| Know your fallback | see the table at the end |
| Roles | one person talks, one person clicks, so the talker never looks down |

The launcher wipes and recreates the demo ledger every time, so you always start from the same 8 settled decisions. Don't relaunch it in the middle of a session.

---

## A. The 2-minute run

**0:00 The problem (15 s), no screen yet.**
"We all make decisions with AI now: ChatGPT, Claude, coding agents. Weeks later an agent cheerfully undoes one, because nothing remembers what was settled, or why. Platform memories are siloed, and none of them track decisions."

**0:15 What it is (10 s), show the wall.**
"Sthira reads your AI history with an open-weight model, keeps every decision with its reason and your exact words, and never deletes anything." *Drag the Rewind slider back and forward once:* "This is what I had decided on 4 March, and now."

**0:25 The moment (30 s), live site or desktop window.**
*Click the MongoDB example.* Narrate over the three stage pills and the typing: "Search, judge, double-check." Pause on the **OVERRULED** stamp and let it land.
"Your agent wanted to migrate to MongoDB. Sthira stops it, shows the exact sentence from March where you ruled that out, and asks if you changed your mind."

**0:55 It works while you're away (25 s), desktop window.**
*Click "Send an agent to work on the app".* Keep talking for about 10 seconds, then the red card and the toast arrive.
"Nobody asked it anything. It's watching my Claude Code sessions, caught the agent going against two decisions, and cited both."

**1:20 It learns (O2) (25 s).**
Go to **To review**, reject one item with a reason ("small talk is not a decision"). Point at **It learns from you**: "That reason is now a rule on every future run. On a 4B model, precision on unseen conversations went from 60% to 71%, and a second critic pass took contradiction checks from 4 of 6 to 6 of 6."

**1:45 Close (15 s).**
"Open source, MIT, local-first, open-weight Qwen3. Nothing is deleted, everything cites its source. Your AI forgets what you decided. Sthira doesn't."

---

## B. The 5-minute run

Do A, but stretch these parts:

1. **The reader (60 s, run it local if time allows).** Drag `demo\chatgpt\export-march.json` into **Feed it your history**. Point out the document lighting up, "2 of 5", and the ETA. "That's real progress, not a fake bar: the ETA starts from a guess and corrects itself from measured chunk times." Open **To review**, **Settle** one (thunk), and show the quote is verified against the source.
2. **I changed my mind (30 s).** Run the MongoDB check, click **I changed my mind**, give a reason. The old stone cracks away and lands in **History**. Drag **Rewind** back: "the old decision is still there on 4 March."
3. **Inside a real agent (60 s), only if `claude mcp list` shows sthira connected.** In Claude Code: "Migrate our user store from Postgres to MongoDB. Check with sthira first." Show Claude calling `check` and stopping. If this has not been verified, skip it and show the `AGENTS.md` block instead.
4. **We used it on ourselves (30 s).** "We pointed Sthira at the session where we built it: 143 messages, 24 entries. It found the real decisions (the name, dropping the Hacktoberfest-PR angle), and it also got things wrong. It logged chatter as 'the user decided…'. That's why a person reviews every entry. And running it found a real bug: rate-limited chunks were skipped silently, which we fixed."
5. **Honest limits (30 s).** See the list below. Judges trust a team that says what it can't do.

---

## If something goes wrong

| What you see | Do this |
|---|---|
| Check says "The model is busy" (Groq rate limit, about 4 to 6 checks a minute) | Click one of the **four example chips**. They fall back to verdicts recorded from a real local Qwen3 run, and the page says so. |
| Hosted model down or no Wi-Fi | Relaunch the desktop demo with `-Local`. Slower (20 to 40 s per step), so narrate: "this is the version where nothing leaves the laptop." |
| Desktop window blank or crashed | Switch to the live site tab. Same product, same moments, except the background watcher. |
| The agent alert doesn't appear in 20 s | Say "it reads sessions when they stop changing", click **Send an agent** once more, and carry on with the next section. Don't click it five times (it spends the rate limit). |
| Reader finishes in 2 s (hosted model is fast) | Say so: "on a laptop CPU this takes about 25 s per chunk, which is why the ETA matters." |
| A judge asks to try their own text | Let them. The keyword fallback still catches rejected alternatives if the model is offline, and labels itself. |

## Numbers you can say (all measured on a laptop, one scenario, written by us)

- Extraction precision on unseen conversations: **0.60 to 0.71** after one round of corrections (qwen3:4b); recall 0.80. The 8B model scored 1.0 with nothing to correct.
- Contradiction checks: **4 of 6 to 6 of 6** with the critic pass (3 real conflicts, 3 traps such as "add a cache").
- Alert from the desktop watcher: about **9 seconds** on the hosted model.
- 143-message self-test: **24 entries**, with errors we listed.
- **55 tests**, CI on Python 3.11 and 3.13. 5 input formats (ChatGPT, Claude.ai, Claude Code, meeting transcripts, subtitles) plus Gemini.

**Do not claim:** that it was tested inside a live Claude Code session until it has been; any ShipWright leaderboard position; that the numbers are a benchmark (it is one small scenario); that this replaces vendor memory.

## Likely questions

- **Why not just use ChatGPT or Claude memory?** They are siloed per vendor, other tools can't read them, and none treats decisions, reasons or contradictions as first-class. Sthira is cross-tool, and the data is yours.
- **How do you stop made-up memories?** Every quote must exist word for word in the source, otherwise the entry is dropped. New entries stay quarantined until a human settles them.
- **What about memory poisoning?** Same answer: nothing becomes settled without a person, and every entry keeps its provenance.
- **How is this different from Mem0 and similar?** They store facts about you. Sthira stores decisions with reasons and history, and checks new work against them. (We read about 80 projects before building; the full prior-art report is in `docs/research/`.)
- **Why open-weight?** Your AI history is private. A 4B model on a laptop is enough to read it, so nothing has to leave your machine. The live site uses a hosted open-weight model for speed.
- **How does it meet O2?** It retains context across tools; it learns from corrections (rejections and verdict corrections become rules); and it corrects its own mistakes (quotes verified against the source, and a critic pass on every warning).
- **What would you build next?** Voice notes, Obsidian and git hooks, assumption watchers ("you chose X because Y; Y just changed"), and sharing a ledger across a team. New sources are small files, so they're easy first contributions, and we already opened good-first issues.
- **Who built what?** Fill this in before the demo: Ojas (lead, core engine, desktop app, UI), Vidit (web and backend: [your PRs]), Danica ([your part]).
