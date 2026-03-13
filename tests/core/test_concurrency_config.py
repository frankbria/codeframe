"""Tests for per-state concurrency limits in batch execution."""

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.v2


class TestConcurrencyConfig:
    """Test ConcurrencyConfig dataclass."""

    def test_defaults(self) -> None:
        from codeframe.core.conductor import ConcurrencyConfig

        cfg = ConcurrencyConfig()
        assert cfg.max_parallel == 4
        assert cfg.by_status == {}

    def test_custom_values(self) -> None:
        from codeframe.core.conductor import ConcurrencyConfig

        cfg = ConcurrencyConfig(max_parallel=8, by_status={"READY": 3, "IN_PROGRESS": 2})
        assert cfg.max_parallel == 8
        assert cfg.by_status["READY"] == 3

    def test_get_limit_for_status_configured(self) -> None:
        from codeframe.core.conductor import ConcurrencyConfig

        cfg = ConcurrencyConfig(max_parallel=4, by_status={"READY": 2})
        assert cfg.get_limit_for_status("READY") == 2

    def test_get_limit_for_status_fallback_to_global(self) -> None:
        from codeframe.core.conductor import ConcurrencyConfig

        cfg = ConcurrencyConfig(max_parallel=4, by_status={"READY": 2})
        assert cfg.get_limit_for_status("IN_PROGRESS") == 4

    def test_get_limit_for_status_empty_by_status(self) -> None:
        from codeframe.core.conductor import ConcurrencyConfig

        cfg = ConcurrencyConfig(max_parallel=6)
        assert cfg.get_limit_for_status("READY") == 6

    def test_effective_workers_global_limit(self) -> None:
        from codeframe.core.conductor import ConcurrencyConfig

        cfg = ConcurrencyConfig(max_parallel=2, by_status={"READY": 5})
        # Global limit (2) is less than per-status limit (5)
        workers = cfg.effective_workers(statuses=["READY"], group_size=10, global_running=0)
        assert workers == 2

    def test_effective_workers_per_status_limit(self) -> None:
        from codeframe.core.conductor import ConcurrencyConfig

        cfg = ConcurrencyConfig(max_parallel=10, by_status={"READY": 3})
        # Per-status limit (3) is less than global (10)
        workers = cfg.effective_workers(statuses=["READY"], group_size=10, global_running=0)
        assert workers == 3

    def test_effective_workers_group_size_limit(self) -> None:
        from codeframe.core.conductor import ConcurrencyConfig

        cfg = ConcurrencyConfig(max_parallel=10)
        workers = cfg.effective_workers(statuses=["READY"], group_size=2, global_running=0)
        assert workers == 2

    def test_effective_workers_accounts_for_running(self) -> None:
        from codeframe.core.conductor import ConcurrencyConfig

        cfg = ConcurrencyConfig(max_parallel=4)
        workers = cfg.effective_workers(statuses=["READY"], group_size=10, global_running=3)
        assert workers == 1  # Only 1 global slot left

    def test_effective_workers_mixed_statuses(self) -> None:
        from codeframe.core.conductor import ConcurrencyConfig

        cfg = ConcurrencyConfig(max_parallel=10, by_status={"READY": 3, "IN_PROGRESS": 1})
        # Mixed group: bottleneck is IN_PROGRESS (1)
        workers = cfg.effective_workers(statuses=["READY", "IN_PROGRESS"], group_size=5, global_running=0)
        assert workers == 1

    def test_effective_workers_never_negative(self) -> None:
        from codeframe.core.conductor import ConcurrencyConfig

        cfg = ConcurrencyConfig(max_parallel=2)
        workers = cfg.effective_workers(statuses=["READY"], group_size=5, global_running=10)
        assert workers >= 1  # At least 1 worker


class TestBatchConfig:
    """Test BatchConfig in EnvironmentConfig."""

    def test_defaults(self) -> None:
        from codeframe.core.config import EnvironmentConfig

        cfg = EnvironmentConfig()
        assert cfg.batch.max_parallel == 4
        assert cfg.batch.max_parallel_by_status == {}

    def test_from_dict(self) -> None:
        from codeframe.core.config import EnvironmentConfig

        cfg = EnvironmentConfig.from_dict({
            "batch": {
                "max_parallel": 8,
                "max_parallel_by_status": {"READY": 3, "IN_PROGRESS": 2},
            }
        })
        assert cfg.batch.max_parallel == 8
        assert cfg.batch.max_parallel_by_status["READY"] == 3

    def test_roundtrip(self) -> None:
        from codeframe.core.config import BatchConfig, EnvironmentConfig

        orig = EnvironmentConfig(batch=BatchConfig(max_parallel=6, max_parallel_by_status={"READY": 2}))
        d = orig.to_dict()
        restored = EnvironmentConfig.from_dict(d)
        assert restored.batch.max_parallel == 6
        assert restored.batch.max_parallel_by_status["READY"] == 2


class TestStartBatchConcurrency:
    """Test start_batch with concurrency_by_status."""

    def test_start_batch_accepts_concurrency_by_status(self) -> None:
        from codeframe.core.conductor import start_batch

        workspace = MagicMock()
        workspace.id = "w1"

        mock_task = MagicMock()
        mock_task.id = "t1"
        mock_task.title = "Test"

        with patch("codeframe.core.conductor.tasks.get", return_value=mock_task):
            with patch("codeframe.core.conductor._save_batch"):
                with patch("codeframe.core.conductor.events.emit_for_workspace"):
                    with patch("codeframe.core.conductor._execute_serial"):
                        batch = start_batch(
                            workspace, ["t1"],
                            concurrency_by_status={"READY": 2},
                        )

        assert batch.concurrency.by_status == {"READY": 2}
        assert batch.concurrency.max_parallel == 4  # default


class TestParseConcurrencyString:
    """Test parsing of --max-parallel-by-status CLI flag."""

    def test_parse_valid_string(self) -> None:
        from codeframe.core.conductor import parse_concurrency_by_status

        result = parse_concurrency_by_status("READY=3,IN_PROGRESS=2")
        assert result == {"READY": 3, "IN_PROGRESS": 2}

    def test_parse_single_value(self) -> None:
        from codeframe.core.conductor import parse_concurrency_by_status

        result = parse_concurrency_by_status("READY=5")
        assert result == {"READY": 5}

    def test_parse_none_returns_empty(self) -> None:
        from codeframe.core.conductor import parse_concurrency_by_status

        result = parse_concurrency_by_status(None)
        assert result == {}

    def test_parse_empty_returns_empty(self) -> None:
        from codeframe.core.conductor import parse_concurrency_by_status

        result = parse_concurrency_by_status("")
        assert result == {}

    def test_parse_invalid_status_raises(self) -> None:
        from codeframe.core.conductor import parse_concurrency_by_status

        with pytest.raises(ValueError, match="Invalid status"):
            parse_concurrency_by_status("INVALID=3")

    def test_parse_invalid_format_raises(self) -> None:
        from codeframe.core.conductor import parse_concurrency_by_status

        with pytest.raises(ValueError):
            parse_concurrency_by_status("READY:3")
