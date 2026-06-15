"""Per-worker in-memory rate-limit startup warning (issue #678).

In-memory rate limiting keeps separate counters in each worker process, so the
effective limit multiplies by the worker count — silently weakening auth
brute-force protection (the limits added in #644). The server must surface this
at startup: a WARNING when rate limiting is enabled, storage is in-memory, and
more than one worker is configured. Single-worker and Redis-backed deployments
must stay silent and unchanged.
"""

import pytest

from codeframe.ui import server

pytestmark = pytest.mark.v2


@pytest.fixture(autouse=True)
def clean_worker_env(monkeypatch):
    """Each case starts with no worker-count env vars set."""
    monkeypatch.delenv("WEB_CONCURRENCY", raising=False)
    monkeypatch.delenv("UVICORN_WORKERS", raising=False)
    yield


# --- _detect_worker_count -------------------------------------------------


def test_worker_count_defaults_to_one_when_unset():
    assert server._detect_worker_count() == 1


def test_worker_count_reads_web_concurrency(monkeypatch):
    monkeypatch.setenv("WEB_CONCURRENCY", "4")
    assert server._detect_worker_count() == 4


def test_worker_count_reads_uvicorn_workers(monkeypatch):
    monkeypatch.setenv("UVICORN_WORKERS", "2")
    assert server._detect_worker_count() == 2


def test_worker_count_takes_the_max_of_both(monkeypatch):
    monkeypatch.setenv("WEB_CONCURRENCY", "2")
    monkeypatch.setenv("UVICORN_WORKERS", "8")
    assert server._detect_worker_count() == 8


def test_worker_count_ignores_unparseable_values(monkeypatch):
    monkeypatch.setenv("WEB_CONCURRENCY", "not-a-number")
    assert server._detect_worker_count() == 1


def test_worker_count_ignores_blank_and_whitespace(monkeypatch):
    monkeypatch.setenv("WEB_CONCURRENCY", "   ")
    assert server._detect_worker_count() == 1


def test_worker_count_handles_padded_integer(monkeypatch):
    monkeypatch.setenv("WEB_CONCURRENCY", " 3 ")
    assert server._detect_worker_count() == 3


# --- _per_worker_rate_limit_warning --------------------------------------


def test_warning_fires_for_memory_multi_worker():
    msg = server._per_worker_rate_limit_warning(
        enabled=True, storage="memory", worker_count=4
    )
    assert msg is not None
    assert "redis" in msg.lower()
    assert "4" in msg


def test_no_warning_for_redis_storage():
    assert (
        server._per_worker_rate_limit_warning(
            enabled=True, storage="redis", worker_count=4
        )
        is None
    )


def test_no_warning_for_single_worker():
    assert (
        server._per_worker_rate_limit_warning(
            enabled=True, storage="memory", worker_count=1
        )
        is None
    )


def test_no_warning_when_rate_limiting_disabled():
    assert (
        server._per_worker_rate_limit_warning(
            enabled=False, storage="memory", worker_count=4
        )
        is None
    )
