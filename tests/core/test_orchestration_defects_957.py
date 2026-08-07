"""Low-severity orchestration-core defects (issue #957).

Seven independent defects, one test class each:

1. ``agent.py`` imported ``json`` inside a ``try`` whose ``except
   json.JSONDecodeError`` sits far below, so any LLM failure during
   self-correction raised ``UnboundLocalError`` and masked the real provider
   error.
2. ``conductor`` injected a list under ``batch.results['__config_reloads__']``
   into a dict typed ``task_id -> RunStatus``; it leaked into the batch API and
   the CLI.
3. ``blockers.py`` opened SQLite connections with no ``try/finally``, leaking
   one on any exception.
4. ``complete_run`` committed the run COMPLETED *before* ``tasks.update_status``,
   so a rejected transition left run and task permanently divergent.
5. ``--stub`` fabricated completion through the real DONE pipeline, including
   the GitHub auto-close.
6. ``--stall-timeout`` / ``--stall-action`` were silently ignored for
   non-react engines.
7. ``Agent._resolve_tactical_decision`` was dead code with a latent
   ``AttributeError`` (``response.strip()`` on an ``LLMResponse``).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from codeframe.adapters.llm import MockProvider

pytestmark = pytest.mark.v2


def _utc_now():
    return datetime.now(timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
# 1. LLM errors during self-correction must not be masked by UnboundLocalError
# ─────────────────────────────────────────────────────────────────────────────


class TestSelfCorrectionSurfacesProviderError:
    def _agent(self, tmp_path, provider):
        from codeframe.core.agent import Agent

        workspace = MagicMock()
        workspace.id = "ws-1"
        workspace.repo_path = tmp_path
        return Agent(workspace, provider)

    def _failing_gate_result(self):
        from codeframe.core.gates import GateCheck, GateResult, GateStatus

        return GateResult(
            passed=False,
            checks=[
                GateCheck(
                    name="pytest",
                    status=GateStatus.FAILED,
                    output="E   assert 1 == 2",
                )
            ],
        )

    def test_json_is_imported_at_module_level(self):
        """The except handler references json, so it must never be function-local."""
        import codeframe.core.agent as agent_module

        assert hasattr(agent_module, "json"), "json must be a module-level import"

        source = Path(agent_module.__file__).read_text()
        # No function-local `import json` anywhere — that is what rebinds the
        # name and makes the except handler raise UnboundLocalError.
        local_imports = [
            line
            for line in source.splitlines()
            if line.strip() == "import json" and line.startswith(" ")
        ]
        assert local_imports == [], f"function-local import json: {local_imports}"

    def test_provider_exception_propagates_its_own_message(self, tmp_path):
        """A provider blow-up must be logged as itself, not as UnboundLocalError."""
        provider = MockProvider()

        def explode(msgs):
            raise RuntimeError("provider exploded: upstream 503")

        provider.set_response_handler(explode)

        agent = self._agent(tmp_path, provider)
        logged: list[str] = []
        agent._debug_log = lambda msg, **kw: logged.append(str(msg))

        # Must not raise, and must return False (self-correction failed).
        assert agent._attempt_verification_fix(self._failing_gate_result()) is False

        joined = "\n".join(logged)
        assert "provider exploded: upstream 503" in joined
        assert "UnboundLocalError" not in joined
        assert "json" not in joined.lower().split("provider exploded")[0][-80:]


# ─────────────────────────────────────────────────────────────────────────────
# 2. Config-reload bookkeeping must not live in batch.results
# ─────────────────────────────────────────────────────────────────────────────


class TestConfigReloadsOffResults:
    def _batch(self, workspace):
        from codeframe.core.conductor import (
            BatchRun,
            BatchStatus,
            OnFailure,
        )

        return BatchRun(
            id="b-1",
            workspace_id=workspace.id,
            task_ids=["t-1"],
            status=BatchStatus.RUNNING,
            strategy="serial",
            max_parallel=1,
            on_failure=OnFailure.CONTINUE,
            started_at=_utc_now(),
            completed_at=None,
            results={"t-1": "COMPLETED"},
        )

    def test_batchrun_has_a_typed_config_reloads_field(self):
        from codeframe.core.conductor import BatchRun

        assert "config_reloads" in BatchRun.__dataclass_fields__

    def test_reload_recorded_off_results(self, tmp_path):
        from codeframe.core.conductor import _apply_pending_config_reload
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        batch = self._batch(ws)

        reload_state = MagicMock()
        reload_state.has_reloaded_since.return_value = True

        with patch("codeframe.core.conductor._save_batch"):
            _apply_pending_config_reload(
                batch, ws, reload_state, datetime(2020, 1, 1, tzinfo=timezone.utc)
            )

        assert "__config_reloads__" not in batch.results
        assert batch.results == {"t-1": "COMPLETED"}
        assert len(batch.config_reloads) == 1

    def test_reloads_survive_a_save_load_round_trip(self, tmp_path):
        from codeframe.core.conductor import _save_batch, get_batch
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        batch = self._batch(ws)
        batch.config_reloads = ["2026-08-07T12:00:00+00:00"]
        _save_batch(ws, batch)

        loaded = get_batch(ws, "b-1")
        assert loaded is not None
        assert loaded.config_reloads == ["2026-08-07T12:00:00+00:00"]
        assert "__config_reloads__" not in loaded.results

    def test_legacy_rows_are_migrated_out_of_results(self, tmp_path):
        """A DB written before this fix still has the key inside results JSON."""
        import json as _json

        from codeframe.core.conductor import _save_batch, get_batch
        from codeframe.core.workspace import create_or_load_workspace, get_db_connection

        ws = create_or_load_workspace(tmp_path)
        batch = self._batch(ws)
        _save_batch(ws, batch)

        # Simulate the pre-fix on-disk shape.
        conn = get_db_connection(ws)
        try:
            conn.execute(
                "UPDATE batch_runs SET results = ?, config_reloads = NULL WHERE id = ?",
                (
                    _json.dumps(
                        {"t-1": "COMPLETED", "__config_reloads__": ["2026-01-01T00:00:00"]}
                    ),
                    "b-1",
                ),
            )
            conn.commit()
        finally:
            conn.close()

        loaded = get_batch(ws, "b-1")
        assert loaded is not None
        assert "__config_reloads__" not in loaded.results
        assert loaded.results == {"t-1": "COMPLETED"}
        assert loaded.config_reloads == ["2026-01-01T00:00:00"]


# ─────────────────────────────────────────────────────────────────────────────
# 3. blockers.py must not leak SQLite connections
# ─────────────────────────────────────────────────────────────────────────────


class TestBlockersCloseConnections:
    def test_no_bare_conn_close_without_a_context_manager(self):
        """Every get_db_connection in blockers.py is guarded."""
        import codeframe.core.blockers as blockers_module

        source = Path(blockers_module.__file__).read_text().splitlines()
        unguarded = []
        for i, line in enumerate(source, start=1):
            if "get_db_connection(" not in line:
                continue
            # Guarded forms: `with closing(get_db_connection(...))` or an
            # assignment immediately followed by a try:.
            if "closing(" in line:
                continue
            nxt = source[i] if i < len(source) else ""
            if nxt.strip().startswith("try:"):
                continue
            unguarded.append(f"{i}: {line.strip()}")
        assert unguarded == [], f"unguarded connections: {unguarded}"

    def test_connection_closed_when_the_query_raises(self, tmp_path):
        """A real failing query (missing table), not a mocked one."""
        from codeframe.core import blockers
        from codeframe.core.workspace import create_or_load_workspace, get_db_connection

        ws = create_or_load_workspace(tmp_path)

        # Construct the real precondition: the query cannot succeed.
        conn = get_db_connection(ws)
        try:
            conn.execute("DROP TABLE blockers")
            conn.commit()
        finally:
            conn.close()

        opened: list[sqlite3.Connection] = []
        real = blockers.get_db_connection

        def tracking(workspace):
            opened.append(real(workspace))
            return opened[-1]

        with patch.object(blockers, "get_db_connection", tracking):
            with pytest.raises(sqlite3.OperationalError):
                blockers.get(ws, "does-not-matter")

        assert opened, "expected a connection to be opened"
        for conn in opened:
            # A closed connection raises ProgrammingError on use.
            with pytest.raises(sqlite3.ProgrammingError):
                conn.execute("SELECT 1")


# ─────────────────────────────────────────────────────────────────────────────
# 4. complete_run must not leave run and task divergent
# ─────────────────────────────────────────────────────────────────────────────


class TestCompleteRunOrdering:
    def test_rejected_task_transition_leaves_run_running(self, tmp_path):
        from codeframe.core import runtime, tasks
        from codeframe.core.state_machine import InvalidTransitionError
        from codeframe.core.runtime import RunStatus
        from codeframe.core.tasks import TaskStatus
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        task = tasks.create(ws, title="T", description="d")
        run = runtime.start_task_run(ws, task.id)

        with patch.object(
            tasks,
            "update_status",
            side_effect=InvalidTransitionError(TaskStatus.DONE, TaskStatus.DONE),
        ):
            with pytest.raises(InvalidTransitionError):
                runtime.complete_run(ws, run.id)

        # The run must NOT have been committed as COMPLETED — otherwise the run
        # says done and the task says in-progress, permanently.
        reloaded = runtime.get_run(ws, run.id)
        assert reloaded.status == RunStatus.RUNNING
        assert reloaded.completed_at is None

    def test_happy_path_still_completes_both(self, tmp_path):
        from codeframe.core import runtime, tasks
        from codeframe.core.runtime import RunStatus
        from codeframe.core.tasks import TaskStatus
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        task = tasks.create(ws, title="T", description="d")
        run = runtime.start_task_run(ws, task.id)

        result = runtime.complete_run(ws, run.id)

        assert result.status == RunStatus.COMPLETED
        assert runtime.get_run(ws, run.id).status == RunStatus.COMPLETED
        assert tasks.get(ws, task.id).status == TaskStatus.DONE


# ─────────────────────────────────────────────────────────────────────────────
# 5. --stub must not fire the GitHub auto-close
# ─────────────────────────────────────────────────────────────────────────────


class TestStubDoesNotAutoCloseGitHub:
    def test_complete_run_can_opt_out_of_autoclose(self, tmp_path):
        from codeframe.core import runtime, tasks
        from codeframe.core.tasks import TaskStatus
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        task = tasks.create(ws, title="T", description="d")
        run = runtime.start_task_run(ws, task.id)

        with patch.object(tasks, "_dispatch_github_autoclose") as dispatch:
            runtime.complete_run(ws, run.id, github_autoclose=False)

        dispatch.assert_not_called()
        # The transition itself still happened.
        assert tasks.get(ws, task.id).status == TaskStatus.DONE

    def test_autoclose_still_fires_by_default(self, tmp_path):
        from codeframe.core import runtime, tasks
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        task = tasks.create(ws, title="T", description="d")
        run = runtime.start_task_run(ws, task.id)

        with patch.object(tasks, "_dispatch_github_autoclose") as dispatch:
            runtime.complete_run(ws, run.id)

        dispatch.assert_called_once()

    def test_cli_stub_path_opts_out(self):
        """The --stub branch must pass github_autoclose=False."""
        import inspect

        from codeframe.cli import app as cli_app

        source = inspect.getsource(cli_app.work_start)
        stub_branch = source.split("elif stub:", 1)
        assert len(stub_branch) == 2, "expected an `elif stub:` branch"
        assert "github_autoclose=False" in stub_branch[1]


# ─────────────────────────────────────────────────────────────────────────────
# 6. Ignored stall flags must warn
# ─────────────────────────────────────────────────────────────────────────────


class TestIgnoredStallFlagsWarn:
    def test_warns_when_stall_settings_ignored_for_a_non_react_engine(self, caplog):
        from codeframe.core.runtime import _warn_if_stall_settings_ignored

        with caplog.at_level("WARNING"):
            _warn_if_stall_settings_ignored(
                engine="claude-code", stall_timeout_s=120, stall_action="retry"
            )

        text = caplog.text.lower()
        assert "stall" in text
        assert "claude-code" in text

    def test_silent_for_react(self, caplog):
        from codeframe.core.runtime import _warn_if_stall_settings_ignored

        with caplog.at_level("WARNING"):
            _warn_if_stall_settings_ignored(
                engine="react", stall_timeout_s=120, stall_action="retry"
            )
        assert "stall" not in caplog.text.lower()

    def test_silent_when_settings_are_defaults(self, caplog):
        """Only warn when the user actually asked for something we ignore."""
        from codeframe.core.runtime import _warn_if_stall_settings_ignored

        with caplog.at_level("WARNING"):
            _warn_if_stall_settings_ignored(
                engine="claude-code", stall_timeout_s=300, stall_action="blocker"
            )
        assert "stall" not in caplog.text.lower()


# ─────────────────────────────────────────────────────────────────────────────
# 7. Dead method with a latent AttributeError is gone
# ─────────────────────────────────────────────────────────────────────────────


class TestDeadTacticalResolverRemoved:
    def test_method_is_deleted(self):
        from codeframe.core.agent import Agent

        assert not hasattr(Agent, "_resolve_tactical_decision")

    def test_no_references_remain(self):
        import codeframe.core.agent as agent_module

        source = Path(agent_module.__file__).read_text()
        assert "_resolve_tactical_decision" not in source
