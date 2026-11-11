# Sthira: Planned Features and Design Notes

> Status: design/theory document. Items marked **[MVP]** are targeted for the hackathon prototype; the rest are roadmap.

## 1. Purpose

Sthira is a desktop, local-first project memory for developers. It retains decisions, requirements and explanations from meeting transcripts and AI conversations (ChatGPT, Claude), keeps each project separate, and answers questions with verifiable source evidence.

## 2. Core: Project Memory (Ask, Retrieve, Verify) [MVP]

**Ingestion:** parse -> clean -> chunk -> embed -> store.

- Chunk by message or speaker turn (about 300-500 tokens), keep code blocks intact, small overlap.
- Each chunk carries metadata: source, project ID, conversation/message ID, speaker, timestamp, character offsets.
- A short header (source, title, date, speaker) is prepended to each chunk before embedding to improve retrieval.
- Store embedding model name and dimension per chunk so models can be changed safely.

**Retrieval:** hybrid search, filtered by project ID inside the query.

- Vector search (meaning) plus SQLite FTS5 (exact terms/identifiers), merged with Reciprocal Rank Fusion.
- Neighbor chunks (previous/next turn) added for context.
- Fallback: brute-force cosine similarity over BLOB embeddings if a vector extension cannot be packaged.

**Answering:**

- The LLM receives labelled chunks and must cite chunk IDs.
- Citations are validated in code (cited IDs must exist and have been retrieved).
- If evidence is below a threshold, Sthira answers "not enough evidence" instead of guessing.
- Imported text is treated as data, never as instructions (prompt-injection safety).
- Where sources conflict, the latest is preferred and the change is mentioned.

## 3. Import

### 3.1 File import [MVP]

ChatGPT export (conversation tree resolved from the current node), Claude export, transcripts (.vtt/.srt/.txt), Markdown.

- Preview screen listing conversations, with checkboxes and project assignment.
- Duplicate detection by file hash and conversation/message identity; re-imports add only new messages.
- Processing states: pending, processing, completed, failed, with retry.
- Streamed parsing and a background worker for large files; per-conversation error handling.

### 3.2 Browser extension: "Save to Sthira" (one platform, one conversation first [MVP])

**Flow:**

1. User opens a conversation on a supported site and clicks "Save to Sthira".
2. The extension extracts visible message text, speaker roles and metadata (title, URL, time).
3. A preview shows the content; the user chooses a project and approves or dismisses. Nothing is saved just by opening a chat.
4. On approval, the extension sends the conversation to the desktop app, which runs the normal ingestion pipeline.
5. Completeness check: warn if the page appears partially loaded (for example, earlier messages are not scrolled into view).

**Security:**

- Desktop app listens on 127.0.0.1 only, on a local port, with a one-time pairing token.
- Requests must carry the token and come from the extension's origin; web pages are rejected.
- Minimal host permissions; capture only on a user click, never in the background.

**Limitations:**

- Only what the page exposes can be captured; this is not a way to fetch full account history.
- Site interface changes can break extraction and need maintenance.
- Users should follow each platform's terms.
- Alternative transport if needed: native messaging.

## 4. Decisions ledger

- Structured decisions: decision, rationale, status (proposed, approved, superseded), date, evidence chunk IDs.
- LLM-suggested items are shown as "suggested" until the user confirms, edits or rejects them.
- Items without evidence are discarded.

## 5. Decision-conflict check (roadmap, stretch)

The user enters a proposal; Sthira compares it with approved decisions and shows any conflict with both pieces of evidence side by side.

## 6. Other views and exports

- Open questions and action items tabs; timeline of decisions.
- Filters by source, speaker and date.
- **Copy context pack:** compact project summary (key decisions plus open questions) to paste into a new AI chat.
- Export project memory as Markdown/JSON.
- Optional later: MCP server so other AI tools can query a project's memory.

## 7. UI controls

Import (drag and drop), project switcher and New project, Ask box, clickable citation chips with a highlighted source viewer, Show evidence / "Why this answer?" panel, thumbs up/down on answers, source manager (Re-index, Delete source, Delete project), Save to Sthira (extension), Approve / Dismiss on previews, privacy badge and toggle.

## 8. Privacy and deletion

- Data stays on the user's machine; show a visible badge: **Local only** vs **Sends text to provider**, with a user-controlled switch.
- Secret scanning (API keys, tokens) at ingestion, with a warning or masking.
- Deleting a source or project removes chunks, embeddings, FTS rows, extracted decisions and the stored raw file.
- Encryption at rest (for example SQLCipher) and clear retention behaviour: roadmap.

## 9. Evaluation plan

- 15-20 test questions with known answers on prepared demo data.
- Metrics: retrieval hit rate (right chunk in top 5), citation validity, correct abstention.
- Compare vector-only, keyword-only and hybrid retrieval.
  

## 10. Priorities

**MVP:** reliable ingestion, project-scoped hybrid retrieval, grounded answers with citations, evidence display, deletion, one-platform extension.

**Later:** decisions ledger and conflict check, more platforms, context pack, MCP, encryption.
