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
    webview.create_window("Sthira", f"http://127.0.0.1:{port}", width=width, height=height, min_size=(760, 560))
    try:
        webview.start()  # blocks until the window is closed
    finally:
        stop.set()
        server.should_exit = True
