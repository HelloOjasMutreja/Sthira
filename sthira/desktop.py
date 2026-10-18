"""Sthira as a desktop app: the web UI in a native window, with the watcher running behind it.

Everything stays on this machine: the UI is served on a private localhost port, the ledger is the same SQLite file the
CLI uses, and the watcher reads your Claude Code sessions and an inbox folder in the background.
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
from pathlib import Path

from . import config


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(port: int, demo: bool = False):
    """Serve the web UI on 127.0.0.1:port in a background thread. Returns (server, thread) once it is accepting."""
    import uvicorn

    root = str(repo_root())
    if root not in sys.path and (repo_root() / "web").exists():
        sys.path.insert(0, root)  # `web/` sits next to the package in the repo
    os.environ["STHIRA_DB"] = str(config.db_path())  # the same ledger the CLI uses, not the web demo's own
    if not demo:
        os.environ["STHIRA_NO_SEED"] = "1"  # a real ledger must never be filled with demo data
    from web.app import app as fastapi_app

    server = uvicorn.Server(uvicorn.Config(fastapi_app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True, name="sthira-web")
    thread.start()
    deadline = time.time() + 15
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    if not server.started:
        raise RuntimeError("The local Sthira server did not start.")
    return server, thread


def start_watcher(stop: threading.Event, on_event=None) -> threading.Thread:
    from . import watch

    t = threading.Thread(
        target=lambda: watch.run(on_event=on_event, stop=stop.is_set), daemon=True, name="sthira-watch")
    t.start()
    return t


def title_for(proposed: int, alerts: int) -> str:
    """The window title doubles as a badge, so a minimised window still says when something needs you."""
    bits = ([f"{alerts} alert{'s' if alerts != 1 else ''}"] if alerts else []) + ([f"{proposed} to review"] if proposed else [])
    return "Sthira" + (f" ({', '.join(bits)})" if bits else "")


def _badge_loop(window, stop: threading.Event, interval: float = 5.0) -> None:
    from . import store

    seen_alerts = 0
    while not stop.wait(interval):
        try:
            con = store.connect()
            try:
                proposed = con.execute("SELECT COUNT(*) FROM entries WHERE status = 'proposed'").fetchone()[0]
                total_alerts = con.execute("SELECT COUNT(*) FROM activity WHERE kind = 'alert'").fetchone()[0]
            finally:
                con.close()
            unseen = max(0, total_alerts - seen_alerts) if seen_alerts or total_alerts else 0
            window.set_title(title_for(proposed, unseen))
        except Exception:
            continue  # the title is a nicety; never let it take the app down


def main(demo: bool = False, watch_files: bool = True, width: int = 1180, height: int = 860) -> None:
    try:
        import webview
    except ImportError as e:
        raise SystemExit("The desktop window needs pywebview: uv sync --extra desktop --extra web") from e
    port = free_port()
    server, _ = start_server(port, demo=demo)
    stop = threading.Event()
    if watch_files:
        start_watcher(stop)
    window = webview.create_window("Sthira", f"http://127.0.0.1:{port}", width=width, height=height, min_size=(760, 560))
    try:
        webview.start(lambda: _badge_loop(window, stop), debug=False)  # blocks until the window is closed
    finally:
        stop.set()
        server.should_exit = True
