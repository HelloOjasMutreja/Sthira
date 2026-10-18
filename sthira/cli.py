"""`sthira` command line."""

from __future__ import annotations

import sys
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import api, config, store

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

app = typer.Typer(help="Sthira: your AI forgets what you decided. Sthira doesn't.", no_args_is_help=True)
console = Console()

COLORS = {"settled": "green", "proposed": "yellow", "rejected": "red", "superseded": "dim"}


def _entry_table(entries, title: str) -> Table:
    t = Table(title=title, show_lines=False, expand=True)
    t.add_column("id", style="cyan", no_wrap=True)
    t.add_column("kind", no_wrap=True)
    t.add_column("statement", ratio=3)
    t.add_column("status", no_wrap=True)
    t.add_column("source", ratio=1)
    for e in entries:
        t.add_row(e.id, e.kind, e.statement, f"[{COLORS.get(e.status, 'white')}]{e.status}[/]",
                  f"{e.source.title} · {(e.decided_at or '')[:10]}")
    return t


@app.command()
def ingest(path: str, kind: Optional[str] = typer.Option(None, help="chatgpt | claude_ai | gemini | claude_code | transcript")):
    """Import a ChatGPT/Claude export, Claude Code sessions, or transcripts (file, folder or .zip)."""
    r = api.ingest(path, kind)
    console.print(f"[green]Ingested[/] {r['messages']} new messages from {r['sources']} sources.")


@app.command()
def extract(limit: Optional[int] = typer.Option(None, help="Max conversations to process")):
    """Extract decisions and settled context from new messages using the local model."""
    console.print(f"Using [bold]{config.model()}[/] via {config.provider()}…")
    skipped: list[str] = []
    with console.status("Reading…") as status:
        entries = api.extract(limit, on_progress=lambda i, n, t: status.update(f"[{i}/{n}] {t}"), errors=skipped)
    if entries:
        console.print(_entry_table(entries, f"{len(entries)} new entries (proposed, awaiting review)"))
    else:
        console.print("Nothing new worth recording." if not skipped else "No new entries from what could be read.")
    if skipped:
        console.print(f"[yellow]{len(skipped)} chunk(s) could not be read and stay pending. Run `sthira extract` again to continue.[/]")
        console.print(f"[dim]{skipped[0]}[/]")


@app.command("list")
def list_(status: Optional[str] = None, kind: Optional[str] = None, q: Optional[str] = None):
    """Show the ledger."""
    console.print(_entry_table(api.list_entries(status, kind, q), "Ledger"))


@app.command()
def review():
    """Go through proposed entries: [s]ettle, [r]eject (Sthira learns), or [k] skip."""
    pending = api.list_entries(status="proposed")
    if not pending:
        console.print("Nothing to review.")
        return
    for e in pending:
        console.print(Panel(f"[bold]{e.statement}[/]\n\nWhy: {e.rationale or '-'}\n"
                            f"Source: {e.source.title} ({(e.decided_at or '')[:10]})\n“{e.source.quote}”",
                            title=f"{e.kind} · {e.id}"))
        choice = typer.prompt("[s]ettle / [r]eject / [k] skip / [q]uit", default="s").lower()[:1]
        if choice == "q":
            break
        if choice == "s":
            api.review(e.id, "settle")
        elif choice == "r":
            note = typer.prompt("Why? (optional, helps Sthira learn)", default="", show_default=False)
            api.review(e.id, "reject", note or None)


@app.command()
def settle(entry_id: str):
    """Confirm an entry."""
    console.print(_entry_table([api.review(entry_id, "settle")], "Settled"))


@app.command()
def reject(entry_id: str, note: Optional[str] = typer.Option(None, "--note", "-n")):
    """Reject a bad extraction; future extractions learn from it."""
    console.print(_entry_table([api.review(entry_id, "reject", note)], "Rejected"))


@app.command()
def supersede(old_id: str, new_id: str):
    """Replace an old decision with a new one (the old one is kept, marked superseded)."""
    console.print(_entry_table([api.supersede(old_id, new_id)], "Superseded"))


@app.command()
def replace(old_id: str, statement: str, why: str = typer.Option("", "--why", "-w")):
    """Change your mind: settle a new decision and supersede the old one (which is kept as history)."""
    r = api.replace(old_id, statement, why)
    console.print(_entry_table([r["old"], r["new"]], "Superseded → new decision"))


@app.command()
def check(text: str):
    """Check new work against what you've settled."""
    v = api.check(text)
    if v.verdict == "contradicts":
        for c in v.conflicts:
            e = c.entry
            console.print(Panel(
                f"[bold red]Contradicts a settled {e.kind}[/]\n\n{e.statement}\n"
                f"[dim]Decided {(e.decided_at or '')[:10]} in “{e.source.title}”: “{e.source.quote}”[/]\n\n{c.explanation}",
                title="⚠ Sthira", border_style="red"))
    else:
        console.print(Panel(f"[green]{v.verdict}[/] with your settled context.", title="Sthira", border_style="green"))


@app.command()
def correct(text: str, note: str):
    """Tell Sthira a check verdict was wrong; it adapts future checks."""
    api.correct_check(text, note)
    console.print("[green]Noted.[/] Future checks will use this correction.")


@app.command()
def sync(path: Optional[str] = typer.Argument(None, help="Defaults to AGENTS.md, or .cursor/rules/sthira.mdc with --format cursor"),
         fmt: str = typer.Option("agents", "--format", "-f", help="agents (AGENTS.md / CLAUDE.md block) | cursor (Cursor rule)")):
    """Write settled context where coding agents read it: AGENTS.md / CLAUDE.md, or a Cursor rule."""
    if fmt not in ("agents", "cursor"):
        raise typer.BadParameter("format must be 'agents' or 'cursor'")
    api.sync(path, fmt=fmt)
    console.print(f"[green]Updated[/] {path or ('.cursor/rules/sthira.mdc' if fmt == 'cursor' else 'AGENTS.md')}")


@app.command()
def rules():
    """Show what Sthira has learned from your corrections (applied to every future extraction and check)."""
    learned = api.learned_rules()
    if not learned:
        console.print("Nothing learned yet. Reject a bad extraction with a reason, or correct a check verdict.")
        return
    t = Table(title="Learned from you", expand=True)
    t.add_column("applies to", no_wrap=True)
    t.add_column("rule", ratio=3)
    t.add_column("from", ratio=2)
    t.add_column("times", justify="right")
    for r in learned:
        t.add_row(r["applies_to"], r["rule"], r["example"][:80], str(r["examples"]))
    console.print(t)


@app.command()
def rules():
    """Show what Sthira has learned from your corrections (applied to every future extraction and check)."""
    learned = api.learned_rules()
    if not learned:
        console.print("Nothing learned yet. Reject a bad extraction with a reason, or correct a check verdict.")
        return
    t = Table(title="Learned from you", expand=True)
    t.add_column("applies to", no_wrap=True)
    t.add_column("rule", ratio=3)
    t.add_column("from", ratio=2)
    t.add_column("times", justify="right")
    for r in learned:
        t.add_row(r["applies_to"], r["rule"], r["example"][:80], str(r["examples"]))
    console.print(t)


@app.command()
def stats():
    """Show how Sthira's precision changes as it learns from your corrections."""
    s = api.feedback_stats()
    console.print(s)


@app.command()
def mcp():
    """Run the MCP server (stdio) so AI tools can read and check against your ledger."""
    from .mcp_server import main

    main()


@app.command()
def scan(path: str):
    """Check what an AI agent proposed in a session (e.g. a Claude Code .jsonl) against your ledger."""
    with console.status("Checking the agent's proposals…"):
        results = api.scan(path)
    for r in results:
        v = r["verdict"]
        if v.verdict == "contradicts":
            for c in v.conflicts:
                console.print(Panel(
                    f"[bold]Agent said:[/] {r['text'][:300]}\n\n[bold red]Contradicts:[/] {c.entry.statement}\n"
                    f"[dim]Decided {(c.entry.decided_at or '')[:10]} in “{c.entry.source.title}”: “{c.entry.source.quote}”[/]\n\n"
                    f"{c.explanation}", title="⚠ Sthira", border_style="red"))
        else:
            console.print(f"[green]✓ {v.verdict}[/]  {r['text'][:100]}")


@app.command()
def hook():
    """Claude Code hook (UserPromptSubmit): warns the agent and you when a prompt contradicts a settled decision."""
    import json as _json

    try:
        data = _json.loads(sys.stdin.read() or "{}")
    except _json.JSONDecodeError:
        raise typer.Exit(0)
    text = data.get("prompt") or ""
    if not text.strip():
        raise typer.Exit(0)
    con = store.connect()
    if not store.list_entries(con, status="settled", q=text):  # fast path: nothing related, stay silent
        raise typer.Exit(0)
    try:
        v = api.check(text, con=con)
    except Exception:
        raise typer.Exit(0)  # never block the user's agent because Sthira failed
    if v.verdict != "contradicts":
        raise typer.Exit(0)
    notes = [f"- {c.entry.statement} (decided {(c.entry.decided_at or '')[:10]} in \"{c.entry.source.title}\"): {c.explanation}"
             for c in v.conflicts]
    msg = "Sthira: this request contradicts settled decisions:\n" + "\n".join(notes)
    print(_json.dumps({
        "systemMessage": msg,
        "hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext":
                               msg + "\nBefore doing anything, point out the conflict and ask the user whether to keep "
                                     "the old decision or supersede it."},
    }))


@app.command()
def demo(db: str = typer.Option(str(config.db_path().parent / "demo.db"), help="Throwaway DB for the demo")):
    """Run the scripted demo: learning from corrections, then catching an agent's contradictions."""
    from pathlib import Path

    from . import demo as _demo

    result = _demo.run(Path(db), say=console.print)
    console.print(Panel(f"Precision before corrections: [bold]{result['phase1']['precision']}[/]\n"
                        f"Precision after corrections:  [bold green]{result['phase2']['precision']}[/]\n"
                        f"Recall vs gold labels: {result['recall']}",
                        title="Sthira learned from feedback", border_style="green"))


@app.command()
def watch(
    dirs: Optional[list[str]] = typer.Argument(None, help="Folders to watch. Default: ~/.claude/projects and ~/.sthira/inbox"),
    interval: float = typer.Option(10.0, help="Seconds between scans"),
    backfill: bool = typer.Option(False, "--backfill", help="Also ingest files that already exist (slow on a local model)"),
):
    """Keep the ledger current: read new Claude Code sessions and anything dropped in the inbox folder, automatically."""
    import time
    from pathlib import Path

    from . import watch as _watch

    targets = [Path(d).expanduser() for d in dirs] if dirs else _watch.default_dirs()
    console.print(f"Watching {', '.join(str(t) for t in targets)} with [bold]{config.model()}[/] (Ctrl+C to stop)")
    first = True
    try:
        while True:
            con = store.connect()
            try:
                for ev in _watch.scan_once(con, targets, first_run_backfill=backfill or not first):
                    if ev.error:
                        console.print(f"[red]✗[/] {ev.path}: {ev.error}")
                    else:
                        console.print(f"[green]✓[/] {Path(ev.path).name}: {ev.messages} new messages, {ev.entries} proposed entries")
            finally:
                con.close()
            first = False
            time.sleep(interval)
    except KeyboardInterrupt:
        console.print("Stopped.")


@app.command("app")
def desktop_app(
    demo: bool = typer.Option(False, "--demo", help="Start with the Acme Notes demo ledger instead of your own"),
    no_watch: bool = typer.Option(False, "--no-watch", help="Don't watch Claude Code sessions and the inbox folder"),
):
    """Open Sthira as a desktop app: the UI in a native window, with the watcher keeping your ledger current."""
    from . import desktop

    desktop.main(demo=demo, watch_files=not no_watch)


@app.command()
def where():
    """Show where the ledger lives."""
    console.print(str(config.db_path()))


def main():
    from .llm import LLMError

    try:
        app()
    except LLMError as e:
        console.print(f"[bold red]Model error:[/] {e}")
        raise SystemExit(2)


if __name__ == "__main__":
    main()
