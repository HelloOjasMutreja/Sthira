import json
import urllib.request

import pytest

pytest.importorskip("uvicorn")
pytest.importorskip("fastapi")

from sthira import desktop  # noqa: E402


def test_local_server_serves_the_ui_without_demo_data(tmp_path, monkeypatch):
    monkeypatch.setenv("STHIRA_DB", str(tmp_path / "real.db"))
    monkeypatch.setenv("STHIRA_NO_SEED", "x")  # recorded, so the launcher's own setting is undone at teardown
    monkeypatch.delenv("STHIRA_NO_SEED")
    port = desktop.free_port()
    server, thread = desktop.start_server(port)
    try:
        base = f"http://127.0.0.1:{port}"
        html = urllib.request.urlopen(base + "/", timeout=10).read().decode()
        assert "Sthira" in html
        entries = json.loads(urllib.request.urlopen(base + "/api/entries", timeout=10).read())
        assert entries == []  # a real ledger is not seeded with the Acme Notes demo
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def test_demo_flag_keeps_the_demo_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("STHIRA_DB", str(tmp_path / "demo.db"))
    monkeypatch.setenv("STHIRA_NO_SEED", "x")  # recorded, so the launcher's own setting is undone at teardown
    monkeypatch.delenv("STHIRA_NO_SEED")
    port = desktop.free_port()
    server, thread = desktop.start_server(port, demo=True)
    try:
        entries = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/entries", timeout=10).read())
        assert len(entries) > 0
    finally:
        server.should_exit = True
        thread.join(timeout=5)
