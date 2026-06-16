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


# --- _parse_worker_count_from_argv (issue #680) --------------------------


@pytest.mark.parametrize(
    "argv, expected",
    [
        (["uvicorn", "codeframe.ui.server:app", "--workers", "2"], 2),
        (["uvicorn", "app", "--workers=4"], 4),
        (["gunicorn", "-w", "3", "app"], 3),
        (["gunicorn", "-w=5", "app"], 5),
        (["python", "-m", "uvicorn", "app", "--workers", " 6 "], 6),
        # Not present / not a worker flag
        (["uvicorn", "codeframe.ui.server:app"], None),
        (["uvicorn", "app", "--port", "8000"], None),
        # Trailing flag with no value
        (["uvicorn", "app", "--workers"], None),
        # Unparseable / non-positive values are ignored
        (["uvicorn", "app", "--workers", "notanumber"], None),
        (["uvicorn", "app", "--workers", "0"], None),
        (["uvicorn", "app", "--workers", "-2"], None),
        ([], None),
    ],
)
def test_parse_worker_count_from_argv(argv, expected):
    assert server._parse_worker_count_from_argv(argv) == expected


# --- _detect_workers_from_process_tree (issue #680) ----------------------


def test_process_tree_detection_finds_workers_flag(monkeypatch):
    """A `--workers N` on an ancestor cmdline is detected."""
    monkeypatch.setattr(
        server,
        "_iter_ancestor_cmdlines",
        lambda max_depth=8: [
            ["python", "spawn_main"],  # the worker's own bootstrap argv
            ["uvicorn", "codeframe.ui.server:app", "--workers", "3"],  # supervisor
        ],
    )
    assert server._detect_workers_from_process_tree() == 3


def test_process_tree_detection_ignores_non_server_workers_flag(monkeypatch):
    """A `--workers` on a non-uvicorn/gunicorn ancestor must not false-positive.

    A wrapper/test-runner with its own `--workers` flag is skipped; the real
    server ancestor (further up) is the one that counts.
    """
    monkeypatch.setattr(
        server,
        "_iter_ancestor_cmdlines",
        lambda max_depth=8: [
            ["some-wrapper", "--workers", "9"],  # NOT a server → ignored
            ["uvicorn", "codeframe.ui.server:app", "--workers", "2"],  # real one
        ],
    )
    assert server._detect_workers_from_process_tree() == 2


def test_process_tree_detection_ignores_lone_non_server_workers_flag(monkeypatch):
    monkeypatch.setattr(
        server,
        "_iter_ancestor_cmdlines",
        lambda max_depth=8: [["pytest", "-p", "xdist", "--workers", "4"]],
    )
    assert server._detect_workers_from_process_tree() is None


@pytest.mark.parametrize(
    "argv, is_server",
    [
        (["uvicorn", "app"], True),
        (["/usr/bin/uvicorn", "app"], True),
        (["python", "-m", "uvicorn", "app"], True),
        (["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "app"], True),
        (["pytest", "--workers", "4"], False),
        (["some-wrapper", "--workers", "9"], False),
        ([], False),
    ],
)
def test_is_asgi_server_cmdline(argv, is_server):
    assert server._is_asgi_server_cmdline(argv) is is_server


def test_process_tree_detection_returns_none_when_absent(monkeypatch):
    monkeypatch.setattr(
        server, "_iter_ancestor_cmdlines", lambda max_depth=8: [["uvicorn", "app"]]
    )
    assert server._detect_workers_from_process_tree() is None


def test_process_tree_detection_never_raises(monkeypatch):
    """Detection degrades gracefully if the walker blows up."""

    def boom(max_depth=8):
        raise OSError("no /proc here")

    monkeypatch.setattr(server, "_iter_ancestor_cmdlines", boom)
    assert server._detect_workers_from_process_tree() is None


# --- _detect_worker_count integrates env + process tree (issue #680) ------


def test_detect_worker_count_uses_process_tree(monkeypatch):
    """Bare `uvicorn --workers N` (no env vars) is detected via the tree."""
    monkeypatch.setattr(
        server, "_detect_workers_from_process_tree", lambda: 2
    )
    assert server._detect_worker_count() == 2


def test_detect_worker_count_env_wins_when_larger(monkeypatch):
    monkeypatch.setenv("WEB_CONCURRENCY", "8")
    monkeypatch.setattr(
        server, "_detect_workers_from_process_tree", lambda: 2
    )
    assert server._detect_worker_count() == 8


def test_detect_worker_count_tree_wins_when_larger(monkeypatch):
    monkeypatch.setenv("WEB_CONCURRENCY", "2")
    monkeypatch.setattr(
        server, "_detect_workers_from_process_tree", lambda: 5
    )
    assert server._detect_worker_count() == 5


def test_detect_worker_count_falls_back_to_env_on_tree_failure(monkeypatch):
    """If the process-tree scan fails, the env-based result still stands."""
    monkeypatch.setenv("UVICORN_WORKERS", "4")

    def boom():
        raise RuntimeError("unexpected")

    monkeypatch.setattr(server, "_detect_workers_from_process_tree", boom)
    assert server._detect_worker_count() == 4


def test_detect_worker_count_defaults_to_one_with_no_signals(monkeypatch):
    monkeypatch.setattr(
        server, "_detect_workers_from_process_tree", lambda: None
    )
    assert server._detect_worker_count() == 1


# --- _iter_ancestor_cmdlines via a fake /proc (issue #680) ---------------


def test_iter_ancestor_cmdlines_walks_proc(monkeypatch):
    """The walker reads the current process and its ancestors from /proc."""
    # Fake a tiny process tree: 100 (self) -> 50 (supervisor) -> 1 (init)
    cmdlines = {
        100: ["python", "spawn_main"],
        50: ["uvicorn", "app", "--workers", "2"],
        1: ["/sbin/init"],
    }
    ppids = {100: 50, 50: 1, 1: 0}

    monkeypatch.setattr(server.os, "getpid", lambda: 100)
    monkeypatch.setattr(server, "_read_proc_cmdline", lambda pid: cmdlines.get(pid))
    monkeypatch.setattr(server, "_read_proc_ppid", lambda pid: ppids.get(pid))

    result = server._iter_ancestor_cmdlines(max_depth=8)
    assert ["uvicorn", "app", "--workers", "2"] in result
    # And the parser finds the count through it
    assert server._detect_workers_from_process_tree() == 2


def test_iter_ancestor_cmdlines_returns_empty_on_missing_proc(monkeypatch):
    monkeypatch.setattr(server, "_read_proc_cmdline", lambda pid: None)
    monkeypatch.setattr(server, "_read_proc_ppid", lambda pid: None)
    assert server._iter_ancestor_cmdlines(max_depth=8) == []
