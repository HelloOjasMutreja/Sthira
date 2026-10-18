import os
import tempfile
import time

os.environ["STHIRA_DB"] = os.path.join(tempfile.mkdtemp(), "drop.db")

import pytest  # noqa: E402

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from sthira import watch  # noqa: E402
from web.app import app  # noqa: E402

client = TestClient(app)


def test_drop_is_off_unless_demo_mode(monkeypatch):
    monkeypatch.delenv("STHIRA_DEMO_DROP", raising=False)
    assert client.post("/api/demo/drop").status_code == 404
    assert client.get("/api/meta").json()["demo_drop"] is False


def test_drop_puts_a_session_in_the_inbox(monkeypatch):
    monkeypatch.setenv("STHIRA_DEMO_DROP", "1")
    assert client.get("/api/meta").json()["demo_drop"] is True
    name = client.post("/api/demo/drop").json()["dropped"]
    inbox = watch.default_dirs()[-1]
    assert (inbox / name).exists() and name.endswith(".jsonl")


def test_watcher_timing_is_configurable(monkeypatch):
    assert watch.settle_seconds() == 20 and watch.scan_interval() == 10
    monkeypatch.setenv("STHIRA_WATCH_SETTLE", "2")
    monkeypatch.setenv("STHIRA_WATCH_INTERVAL", "2")
    assert watch.settle_seconds() == 2 and watch.scan_interval() == 2
