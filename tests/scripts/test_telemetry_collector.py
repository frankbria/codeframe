"""Smoke tests for scripts/telemetry_collector.py — the minimal beta collector."""

import importlib.util
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.v2

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture
def collector(tmp_path, monkeypatch):
    """Load the collector script with an isolated log path."""
    log_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("TELEMETRY_LOG_PATH", str(log_path))
    spec = importlib.util.spec_from_file_location(
        "telemetry_collector", REPO_ROOT / "scripts" / "telemetry_collector.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return TestClient(module.app), log_path


class TestCollector:
    def test_accepts_batch_and_appends_jsonl(self, collector):
        client, log_path = collector
        events = [
            {"event": "command", "command": "init", "exit_code": 0},
            {"event": "crash", "exception_type": "ValueError"},
        ]
        response = client.post("/v1/events", json={"events": events})
        assert response.status_code == 202
        assert response.json() == {"accepted": 2}

        lines = log_path.read_text().strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["command"] == "init"
        # Each stored line gets a server-side received_at stamp
        assert "received_at" in json.loads(lines[0])

    def test_appends_across_requests(self, collector):
        client, log_path = collector
        client.post("/v1/events", json={"events": [{"event": "command"}]})
        client.post("/v1/events", json={"events": [{"event": "command"}]})
        assert len(log_path.read_text().strip().splitlines()) == 2

    def test_rejects_malformed_body(self, collector):
        client, _ = collector
        assert client.post("/v1/events", json={"nope": 1}).status_code == 422
        assert client.post("/v1/events", json={"events": "not-a-list"}).status_code == 422

    def test_rejects_oversized_batch(self, collector):
        client, log_path = collector
        events = [{"event": "command"}] * 101
        response = client.post("/v1/events", json={"events": events})
        assert response.status_code == 413
        assert not log_path.exists()

    def test_healthz(self, collector):
        client, _ = collector
        assert client.get("/healthz").status_code == 200
