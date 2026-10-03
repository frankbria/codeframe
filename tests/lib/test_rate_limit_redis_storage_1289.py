"""``RATE_LIMIT_STORAGE=redis`` — the documented multi-worker setting — must not
crash ``codeframe serve`` at import (#1289).

redis was not a dependency, and limits raises ``ConfigurationError`` (not the
``ImportError`` the limiter caught) when it is missing, so the server died with
a raw traceback at import. It is now the ``codeframe-ai[redis]`` extra; without
it the error names that extra. Falling back to in-memory counters instead would
multiply every limit — auth brute-force protection included — by the worker
count, the exact problem the setting exists to fix.
"""

import os
import subprocess
import sys

import pytest

pytestmark = pytest.mark.v2

_REDIS_ENV = {
    "RATE_LIMIT_ENABLED": "true",
    "RATE_LIMIT_STORAGE": "redis",
    "REDIS_URL": "redis://127.0.0.1:1/0",  # nothing listens: limits connects lazily
}


def _import_server(prelude: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", prelude + "import codeframe.ui.server\n"],
        env={**os.environ, **_REDIS_ENV},
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_the_server_imports_with_redis_storage_configured():
    result = _import_server()
    assert result.returncode == 0, result.stderr[-2000:]


def test_without_the_extra_the_error_names_it():
    result = _import_server("import sys\nsys.modules['redis'] = None\n")

    assert result.returncode != 0
    last_line = result.stderr.strip().splitlines()[-1]
    assert "codeframe-ai[redis]" in last_line, last_line
    assert "RATE_LIMIT_STORAGE" in last_line, last_line


@pytest.mark.parametrize(
    "url", ["localhost:6379", "http://localhost:6379", "redis+sentinel://localhost:26379"]
)
def test_a_bad_redis_url_is_reported_as_a_bad_url_not_a_missing_extra(url):
    """limits raises ConfigurationError for any bad URI too; telling an operator
    who has the extra to install it sends them the wrong way (internal review)."""
    result = subprocess.run(
        [sys.executable, "-c", "import codeframe.ui.server"],
        env={**os.environ, **_REDIS_ENV, "REDIS_URL": url},
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode != 0
    last_line = result.stderr.strip().splitlines()[-1]
    assert "REDIS_URL" in last_line and "codeframe-ai[redis]" not in last_line, last_line


def test_redis_storage_without_a_url_refuses_instead_of_using_memory():
    """It used to downgrade to per-worker counters with only a WARNING — the
    same multiplication the extra's refusal exists to prevent."""
    env = {**os.environ, **_REDIS_ENV}
    env.pop("REDIS_URL")
    result = subprocess.run(
        [sys.executable, "-c", "import codeframe.ui.server"],
        env=env, capture_output=True, text=True, timeout=120,
    )

    assert result.returncode != 0
    assert "REDIS_URL" in result.stderr.strip().splitlines()[-1]
