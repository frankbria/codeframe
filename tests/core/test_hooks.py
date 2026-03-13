"""Tests for workspace lifecycle hooks system."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.v2


# ---------------------------------------------------------------------------
# HooksConfig tests (Step 1)
# ---------------------------------------------------------------------------


class TestHooksConfig:
    """Test HooksConfig dataclass and integration with EnvironmentConfig."""

    def test_hooks_config_defaults(self) -> None:
        from codeframe.core.config import HooksConfig

        cfg = HooksConfig()
        assert cfg.after_init is None
        assert cfg.before_task is None
        assert cfg.after_task_success is None
        assert cfg.after_task_failure is None
        assert cfg.before_remove is None
        assert cfg.hook_timeout == 60

    def test_hooks_config_with_values(self) -> None:
        from codeframe.core.config import HooksConfig

        cfg = HooksConfig(
            after_init="npm install",
            before_task="git checkout -b cf/{{task_id}}",
            hook_timeout=30,
        )
        assert cfg.after_init == "npm install"
        assert cfg.before_task == "git checkout -b cf/{{task_id}}"
        assert cfg.hook_timeout == 30

    def test_environment_config_has_hooks_field(self) -> None:
        from codeframe.core.config import EnvironmentConfig, HooksConfig

        cfg = EnvironmentConfig()
        assert isinstance(cfg.hooks, HooksConfig)

    def test_environment_config_from_dict_with_hooks(self) -> None:
        from codeframe.core.config import EnvironmentConfig

        data = {
            "hooks": {
                "after_init": "npm install",
                "before_task": "echo starting",
                "hook_timeout": 120,
            }
        }
        cfg = EnvironmentConfig.from_dict(data)
        assert cfg.hooks.after_init == "npm install"
        assert cfg.hooks.before_task == "echo starting"
        assert cfg.hooks.hook_timeout == 120

    def test_environment_config_from_dict_without_hooks(self) -> None:
        from codeframe.core.config import EnvironmentConfig

        cfg = EnvironmentConfig.from_dict({})
        assert cfg.hooks.after_init is None
        assert cfg.hooks.hook_timeout == 60

    def test_environment_config_to_dict_includes_hooks(self) -> None:
        from codeframe.core.config import EnvironmentConfig, HooksConfig

        cfg = EnvironmentConfig(hooks=HooksConfig(after_init="make build"))
        d = cfg.to_dict()
        assert "hooks" in d
        assert d["hooks"]["after_init"] == "make build"

    def test_roundtrip_serialization(self) -> None:
        from codeframe.core.config import EnvironmentConfig, HooksConfig

        original = EnvironmentConfig(
            hooks=HooksConfig(
                before_task="echo {{task_id}}",
                after_task_success="git commit -m done",
                hook_timeout=45,
            )
        )
        d = original.to_dict()
        restored = EnvironmentConfig.from_dict(d)
        assert restored.hooks.before_task == original.hooks.before_task
        assert restored.hooks.after_task_success == original.hooks.after_task_success
        assert restored.hooks.hook_timeout == 45


# ---------------------------------------------------------------------------
# Template rendering tests (Step 2)
# ---------------------------------------------------------------------------


class TestRenderHookCommand:
    """Test Jinja2 template variable rendering."""

    def test_renders_task_id(self) -> None:
        from codeframe.core.hooks import HookContext, render_hook_command

        ctx = HookContext(task_id="abc123", task_title="Fix bug", task_status="in_progress", workspace_path="/tmp/repo")
        result = render_hook_command("git checkout -b cf/{{task_id}}", ctx)
        assert result == "git checkout -b cf/abc123"

    def test_renders_multiple_variables(self) -> None:
        from codeframe.core.hooks import HookContext, render_hook_command

        ctx = HookContext(task_id="t1", task_title="Add feature", task_status="done", workspace_path="/ws")
        result = render_hook_command("echo {{task_id}} {{task_title}} {{task_status}}", ctx)
        assert result == "echo t1 Add feature done"

    def test_renders_workspace_path(self) -> None:
        from codeframe.core.hooks import HookContext, render_hook_command

        ctx = HookContext(task_id="", task_title="", task_status="init", workspace_path="/home/user/repo")
        result = render_hook_command("cd {{workspace_path}} && npm install", ctx)
        assert result == "cd /home/user/repo && npm install"

    def test_passes_through_non_template_text(self) -> None:
        from codeframe.core.hooks import HookContext, render_hook_command

        ctx = HookContext(task_id="t1", task_title="", task_status="", workspace_path="")
        result = render_hook_command("echo hello world", ctx)
        assert result == "echo hello world"


# ---------------------------------------------------------------------------
# Hook execution tests (Step 2)
# ---------------------------------------------------------------------------


class TestRunHook:
    """Test hook subprocess execution."""

    def test_successful_execution(self) -> None:
        from codeframe.core.hooks import HookContext, run_hook

        ctx = HookContext(task_id="t1", task_title="", task_status="", workspace_path="/tmp")
        result = run_hook("test_hook", "echo hello", Path("/tmp"), ctx, timeout=10)
        assert result.success is True
        assert result.hook_name == "test_hook"
        assert "hello" in result.stdout
        assert result.timed_out is False

    def test_failed_execution(self) -> None:
        from codeframe.core.hooks import HookContext, run_hook

        ctx = HookContext(task_id="t1", task_title="", task_status="", workspace_path="/tmp")
        result = run_hook("test_hook", "exit 1", Path("/tmp"), ctx, timeout=10)
        assert result.success is False
        assert result.timed_out is False

    def test_timeout_enforcement(self) -> None:
        from codeframe.core.hooks import HookContext, run_hook

        ctx = HookContext(task_id="t1", task_title="", task_status="", workspace_path="/tmp")
        result = run_hook("test_hook", "sleep 10", Path("/tmp"), ctx, timeout=1)
        assert result.success is False
        assert result.timed_out is True

    def test_renders_template_before_execution(self) -> None:
        from codeframe.core.hooks import HookContext, run_hook

        ctx = HookContext(task_id="my-task", task_title="", task_status="", workspace_path="/tmp")
        result = run_hook("test_hook", "echo {{task_id}}", Path("/tmp"), ctx, timeout=10)
        assert result.success is True
        assert "my-task" in result.stdout

    def test_captures_stderr(self) -> None:
        from codeframe.core.hooks import HookContext, run_hook

        ctx = HookContext(task_id="t1", task_title="", task_status="", workspace_path="/tmp")
        result = run_hook("test_hook", "echo error >&2", Path("/tmp"), ctx, timeout=10)
        assert "error" in result.stderr

    def test_duration_tracked(self) -> None:
        from codeframe.core.hooks import HookContext, run_hook

        ctx = HookContext(task_id="t1", task_title="", task_status="", workspace_path="/tmp")
        result = run_hook("test_hook", "echo fast", Path("/tmp"), ctx, timeout=10)
        assert result.duration_ms >= 0


# ---------------------------------------------------------------------------
# execute_hook orchestrator tests (Step 2)
# ---------------------------------------------------------------------------


class TestExecuteHook:
    """Test the execute_hook orchestrator."""

    def test_returns_none_when_hook_not_configured(self) -> None:
        from codeframe.core.config import EnvironmentConfig
        from codeframe.core.hooks import HookContext, execute_hook

        config = EnvironmentConfig()
        ctx = HookContext(task_id="t1", task_title="", task_status="", workspace_path="/tmp")
        result = execute_hook("before_task", config, Path("/tmp"), ctx, abort_on_failure=True)
        assert result is None

    def test_executes_configured_hook(self) -> None:
        from codeframe.core.config import EnvironmentConfig, HooksConfig
        from codeframe.core.hooks import HookContext, execute_hook

        config = EnvironmentConfig(hooks=HooksConfig(before_task="echo running"))
        ctx = HookContext(task_id="t1", task_title="", task_status="", workspace_path="/tmp")
        result = execute_hook("before_task", config, Path("/tmp"), ctx, abort_on_failure=False)
        assert result is not None
        assert result.success is True

    def test_abort_on_failure_raises(self) -> None:
        from codeframe.core.config import EnvironmentConfig, HooksConfig
        from codeframe.core.hooks import HookAbortError, HookContext, execute_hook

        config = EnvironmentConfig(hooks=HooksConfig(before_task="exit 1"))
        ctx = HookContext(task_id="t1", task_title="", task_status="", workspace_path="/tmp")
        with pytest.raises(HookAbortError):
            execute_hook("before_task", config, Path("/tmp"), ctx, abort_on_failure=True)

    def test_no_abort_on_failure_logs_warning(self) -> None:
        from codeframe.core.config import EnvironmentConfig, HooksConfig
        from codeframe.core.hooks import HookContext, execute_hook

        config = EnvironmentConfig(hooks=HooksConfig(after_task_failure="exit 1"))
        ctx = HookContext(task_id="t1", task_title="", task_status="", workspace_path="/tmp")
        # Should not raise, just return the failed result
        result = execute_hook("after_task_failure", config, Path("/tmp"), ctx, abort_on_failure=False)
        assert result is not None
        assert result.success is False

    def test_uses_hook_timeout_from_config(self) -> None:
        from codeframe.core.config import EnvironmentConfig, HooksConfig
        from codeframe.core.hooks import HookContext, execute_hook

        config = EnvironmentConfig(hooks=HooksConfig(before_task="sleep 10", hook_timeout=1))
        ctx = HookContext(task_id="t1", task_title="", task_status="", workspace_path="/tmp")
        with pytest.raises(Exception):  # HookAbortError because abort_on_failure=True
            execute_hook("before_task", config, Path("/tmp"), ctx, abort_on_failure=True)


# ---------------------------------------------------------------------------
# HookAbortError tests
# ---------------------------------------------------------------------------


class TestHookAbortError:
    """Test HookAbortError exception."""

    def test_message_contains_hook_name(self) -> None:
        from codeframe.core.hooks import HookAbortError, HookResult

        result = HookResult(
            hook_name="before_task", command="exit 1", success=False,
            stdout="", stderr="permission denied", duration_ms=50, timed_out=False,
        )
        err = HookAbortError("before_task", result)
        assert "before_task" in str(err)
        assert "permission denied" in str(err)

    def test_stores_result(self) -> None:
        from codeframe.core.hooks import HookAbortError, HookResult

        result = HookResult(
            hook_name="before_task", command="exit 1", success=False,
            stdout="", stderr="fail", duration_ms=10, timed_out=False,
        )
        err = HookAbortError("before_task", result)
        assert err.result is result
        assert err.hook_name == "before_task"
