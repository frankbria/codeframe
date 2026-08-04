"""Batch reconciliation against linked GitHub issue state (#1032).

#921 deleted the ``github_checker`` parameter because it was passed at neither
call site — an advertised capability that did not exist. This is the feature it
was standing in for, built with the auth, caching and failure behavior the
parameter never had.

The expensive part is the loop, not the call: reconciliation ticks every 30s
over every active task, so the tests below pin the three things that keep it
from exhausting a single machine-wide PAT — no linked issue means no call, a
cached answer means no call, and a failure disables the checker instead of
retrying forever.
"""

from datetime import datetime

import pytest

from codeframe.core.reconciliation import GitHubIssueState, ReconciliationEngine
from codeframe.core.state_machine import TaskStatus
from codeframe.core.tasks import Task

pytestmark = pytest.mark.v2

ISSUE_URL = "https://github.com/acme/app/issues/42"


def make_task(
    *,
    task_id="t1",
    status=TaskStatus.IN_PROGRESS,
    issue_number=42,
    external_url=ISSUE_URL,
):
    return Task(
        id=task_id,
        workspace_id="w1",
        prd_id=None,
        title="Imported task",
        description="",
        status=status,
        priority=0,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        github_issue_number=issue_number,
        external_url=external_url,
    )


class FakeGitHub:
    """Stubbed issue fetch that records every call it receives."""

    def __init__(self, state="closed", raises=None):
        self.state = state
        self.raises = raises
        self.calls = []

    def __call__(self, pat, repo, number):
        self.calls.append((pat, repo, number))
        if self.raises is not None:
            raise self.raises
        return self.state


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


# ---------------------------------------------------------------------------
# AC2: tasks without a linked issue cost zero API calls
# ---------------------------------------------------------------------------


class TestNoLinkedIssueCostsNothing:
    def test_task_without_issue_number_never_calls_github(self):
        gh = FakeGitHub()
        checker = GitHubIssueState(fetch=gh, pat="tok")

        assert checker.is_closed(make_task(issue_number=None)) is False
        assert gh.calls == []

    def test_task_without_external_url_never_calls_github(self):
        """A linked number with no source URL has no repo to ask about."""
        gh = FakeGitHub()
        checker = GitHubIssueState(fetch=gh, pat="tok")

        assert checker.is_closed(make_task(external_url=None)) is False
        assert gh.calls == []

    def test_a_batch_of_unlinked_tasks_makes_no_calls_across_many_ticks(self):
        gh = GitHubIssueState(fetch=(fake := FakeGitHub()), pat="tok")
        tasks_ = [make_task(task_id=f"t{i}", issue_number=None) for i in range(20)]

        for _ in range(10):  # ten reconciliation ticks
            for t in tasks_:
                gh.is_closed(t)

        assert fake.calls == []


# ---------------------------------------------------------------------------
# AC1: a closed issue is detected and recorded as an external completion
# ---------------------------------------------------------------------------


class TestClosedIssueDetected:
    def test_closed_issue_reports_closed(self):
        checker = GitHubIssueState(fetch=FakeGitHub(state="closed"), pat="tok")
        assert checker.is_closed(make_task()) is True

    def test_open_issue_reports_not_closed(self):
        checker = GitHubIssueState(fetch=FakeGitHub(state="open"), pat="tok")
        assert checker.is_closed(make_task()) is False

    def test_repo_comes_from_the_tasks_own_source_url(self):
        """Matches auto-close (#565): the task's source repo, not the
        workspace's current connection — a workspace may have been reconnected
        to a different repository since the import."""
        gh = FakeGitHub()
        checker = GitHubIssueState(fetch=gh, pat="tok")
        checker.is_closed(
            make_task(external_url="https://github.com/other/repo/issues/7", issue_number=7)
        )
        assert gh.calls == [("tok", "other/repo", 7)]

    def test_engine_emits_a_completed_change_sourced_to_github(self, monkeypatch):
        task = make_task()
        monkeypatch.setattr(
            "codeframe.core.tasks.get", lambda ws, tid: task
        )
        engine = ReconciliationEngine(
            workspace=object(),
            issue_state=GitHubIssueState(fetch=FakeGitHub(state="closed"), pat="tok"),
        )

        changes = engine.check_task("t1")

        assert len(changes) == 1
        assert changes[0].change_type == "completed"
        assert changes[0].source == "github"
        assert changes[0].details["issue_number"] == 42

    def test_completed_change_lands_in_batch_results_as_COMPLETED(self, monkeypatch):
        """apply_changes maps 'completed' -> COMPLETED and 'closed' -> FAILED.
        An issue closed on GitHub is a completion, not a failure."""
        task = make_task()
        monkeypatch.setattr("codeframe.core.tasks.get", lambda ws, tid: task)
        engine = ReconciliationEngine(
            workspace=object(),
            issue_state=GitHubIssueState(fetch=FakeGitHub(state="closed"), pat="tok"),
        )

        class Batch:
            results = {}

        result = engine.check_all_active(["t1"])
        batch = Batch()
        engine.apply_changes(result, batch, {})

        assert batch.results["t1"] == "COMPLETED"
        assert result.tasks_skipped == ["t1"]

    def test_already_done_task_is_not_charged_a_github_call(self, monkeypatch):
        """The local DONE check already fires; asking GitHub would be a wasted
        call on every tick for every finished task."""
        task = make_task(status=TaskStatus.DONE)
        monkeypatch.setattr("codeframe.core.tasks.get", lambda ws, tid: task)
        gh = FakeGitHub()
        engine = ReconciliationEngine(
            workspace=object(), issue_state=GitHubIssueState(fetch=gh, pat="tok")
        )

        changes = engine.check_task("t1")

        assert [c.source for c in changes] == ["manual"]
        assert gh.calls == []


# ---------------------------------------------------------------------------
# AC4: call counts stay bounded across several ticks
# ---------------------------------------------------------------------------


class TestCallCountsStayBounded:
    def test_repeated_ticks_within_the_open_ttl_make_one_call(self):
        gh = FakeGitHub(state="open")
        clock = FakeClock()
        checker = GitHubIssueState(fetch=gh, pat="tok", open_ttl_seconds=60, now=clock)
        task = make_task()

        checker.is_closed(task)
        clock.advance(30)  # one tick later, still inside the TTL
        checker.is_closed(task)

        assert len(gh.calls) == 1

    def test_an_open_issue_is_rechecked_soon_enough_to_catch_a_closure(self):
        """An "open" answer must go stale fast. Caching it for minutes on a 30s
        loop means a closure lands, the task is reached, and the agent runs
        anyway — the very case this feature exists to prevent."""
        gh = FakeGitHub(state="open")
        clock = FakeClock()
        checker = GitHubIssueState(fetch=gh, pat="tok", now=clock)
        task = make_task()

        checker.is_closed(task)
        clock.advance(90)  # three ticks
        gh.state = "closed"

        assert checker.is_closed(task) is True, (
            "a closure was invisible for longer than a batch takes to reach "
            "the next task"
        )

    def test_ten_ticks_over_an_open_issue_stay_bounded(self):
        """Rechecking sooner must not mean rechecking every tick."""
        gh = FakeGitHub(state="open")
        clock = FakeClock()
        checker = GitHubIssueState(fetch=gh, pat="tok", now=clock)
        task = make_task()

        for _ in range(10):  # 300s of batch time at the 30s interval
            checker.is_closed(task)
            clock.advance(30)

        assert len(gh.calls) <= 5, (
            f"{len(gh.calls)} calls for one issue over 10 ticks is not bounded"
        )

    def test_distinct_issues_are_cached_separately(self):
        gh = FakeGitHub(state="open")
        checker = GitHubIssueState(fetch=gh, pat="tok", now=FakeClock())
        a = make_task(task_id="a", issue_number=1, external_url="https://github.com/acme/app/issues/1")
        b = make_task(task_id="b", issue_number=2, external_url="https://github.com/acme/app/issues/2")

        for _ in range(5):
            checker.is_closed(a)
            checker.is_closed(b)

        assert len(gh.calls) == 2

    def test_a_closed_answer_is_never_refetched(self):
        """Closed is effectively terminal for a batch's lifetime — unlike
        "open", it cannot go stale in a way that matters here."""
        gh = FakeGitHub(state="closed")
        clock = FakeClock()
        checker = GitHubIssueState(fetch=gh, pat="tok", now=clock)
        task = make_task()

        for _ in range(10):
            assert checker.is_closed(task) is True
            clock.advance(600)

        assert len(gh.calls) == 1


# ---------------------------------------------------------------------------
# AC3: an outage or missing PAT logs once and leaves the batch unaffected
# ---------------------------------------------------------------------------


class TestDegradesQuietly:
    def test_missing_pat_makes_no_calls_and_never_raises(self, monkeypatch):
        # Stub the resolver rather than passing pat=None: pat=None means
        # "resolve it lazily", which on a developer machine with a stored PAT
        # would find one and make the call this test says never happens.
        monkeypatch.setattr(
            "codeframe.core.reconciliation._default_pat", lambda: None
        )
        gh = FakeGitHub()
        checker = GitHubIssueState(fetch=gh)

        assert checker.is_closed(make_task()) is False
        assert gh.calls == []

    def test_missing_pat_stops_further_lookups(self, monkeypatch):
        """One PAT lookup for the batch, not one per task per tick."""
        lookups = []
        monkeypatch.setattr(
            "codeframe.core.reconciliation._default_pat",
            lambda: lookups.append(1) or None,
        )
        checker = GitHubIssueState(fetch=FakeGitHub(), now=FakeClock())

        for _ in range(10):
            checker.is_closed(make_task())

        assert len(lookups) == 1

    def test_github_failure_does_not_propagate(self):
        checker = GitHubIssueState(
            fetch=FakeGitHub(raises=RuntimeError("GitHub is down")), pat="tok"
        )
        assert checker.is_closed(make_task()) is False

    def test_after_a_failure_the_checker_stops_calling_github(self):
        """Retrying every 30s through an outage is how you get rate-limited."""
        gh = FakeGitHub(raises=RuntimeError("GitHub is down"))
        clock = FakeClock()
        checker = GitHubIssueState(fetch=gh, pat="tok", now=clock)
        task = make_task()

        for _ in range(10):
            checker.is_closed(task)
            clock.advance(30)

        assert len(gh.calls) == 1

    def test_a_failure_is_logged_once_not_every_tick(self, caplog):
        gh = FakeGitHub(raises=RuntimeError("GitHub is down"))
        checker = GitHubIssueState(fetch=gh, pat="tok", now=FakeClock())
        task = make_task()

        with caplog.at_level("WARNING"):
            for _ in range(10):
                checker.is_closed(task)

        warnings = [r for r in caplog.records if "GitHub is down" in r.getMessage()]
        assert len(warnings) == 1

    def test_engine_survives_a_github_outage_and_reports_no_changes(self, monkeypatch):
        task = make_task()
        monkeypatch.setattr("codeframe.core.tasks.get", lambda ws, tid: task)
        monkeypatch.setattr(
            "codeframe.core.blockers.list_for_task", lambda ws, tid: []
        )
        engine = ReconciliationEngine(
            workspace=object(),
            issue_state=GitHubIssueState(
                fetch=FakeGitHub(raises=RuntimeError("boom")), pat="tok"
            ),
        )

        result = engine.check_all_active(["t1"])

        assert result.changes_detected == []
        assert result.errors == []  # an outage is not a reconciliation error


# ---------------------------------------------------------------------------
# Wiring: the engine builds a real checker when none is injected
# ---------------------------------------------------------------------------


class TestWiredByDefault:
    def test_engine_has_an_issue_state_checker_without_injection(self):
        engine = ReconciliationEngine(workspace=object())
        assert isinstance(engine._issue_state, GitHubIssueState)

    def test_conductor_thread_does_not_need_a_checker_argument(self):
        """#921's invariant holds: no advertised-but-unwired parameter. The
        checker is constructed by the engine, so both call sites get it."""
        import inspect

        from codeframe.core import conductor

        params = inspect.signature(conductor._start_reconciliation_thread).parameters
        assert "github_checker" not in params

    def test_default_fetch_reads_state_from_the_issues_service(self):
        """The default fetch must ask for something get_issue actually returns."""
        from codeframe.core.github_issues_service import GitHubIssueDetail

        assert "state" in GitHubIssueDetail.__annotations__


class TestLocalTaskRowFollowsTheClosedIssue:
    """Recording the batch result alone leaves the system inconsistent.

    The ``source="manual"`` path is consistent for free: the task row is
    *already* DONE, which is how the change was detected. Nothing sets the row
    for a GitHub closure, so without this the batch finishes COMPLETED while
    the board still shows the task READY — and the next batch runs it again.

    ``READY -> DONE`` is not a permitted transition, so a task the batch had not
    started yet must pass through IN_PROGRESS, the same path a real run takes.
    """

    @pytest.fixture
    def workspace(self, tmp_path):
        from codeframe.core.workspace import create_or_load_workspace

        ws_dir = tmp_path / "ws"
        ws_dir.mkdir(parents=True, exist_ok=True)
        return create_or_load_workspace(ws_dir)

    def _task_with_closed_issue(self, workspace, status):
        from codeframe.core import tasks as tasks_mod

        # BACKLOG is what tasks.create defaults to, and what the GitHub
        # importer uses; walk forward from there to whatever the test wants.
        task = tasks_mod.create(
            workspace,
            title="imported",
            description="",
            github_issue_number=42,
            external_url=ISSUE_URL,
        )
        path = {
            TaskStatus.BACKLOG: [],
            TaskStatus.READY: [TaskStatus.READY],
            TaskStatus.IN_PROGRESS: [TaskStatus.READY, TaskStatus.IN_PROGRESS],
        }[status]
        for step in path:
            tasks_mod.update_status(workspace, task.id, step)
        return task

    def _reconcile(self, workspace, task_id):
        engine = ReconciliationEngine(
            workspace=workspace,
            issue_state=GitHubIssueState(fetch=FakeGitHub(state="closed"), pat="tok"),
        )
        result = engine.check_all_active([task_id])

        class Batch:
            id = "b1"
            results = {}

        batch = Batch()
        engine.apply_changes(result, batch, {})
        return result, batch

    def test_a_not_yet_started_task_is_marked_DONE(self, workspace):
        from codeframe.core import tasks as tasks_mod

        task = self._task_with_closed_issue(workspace, TaskStatus.READY)

        _, batch = self._reconcile(workspace, task.id)

        assert batch.results[task.id] == "COMPLETED"
        assert tasks_mod.get(workspace, task.id).status == TaskStatus.DONE, (
            "batch says COMPLETED but the board still shows the task undone, "
            "so the next batch will run it again"
        )

    def test_a_backlog_task_is_marked_DONE(self, workspace):
        """BACKLOG is what the GitHub importer creates, so this is the primary
        case, not an edge one — and BACKLOG only permits READY."""
        from codeframe.core import tasks as tasks_mod

        task = self._task_with_closed_issue(workspace, TaskStatus.BACKLOG)
        assert tasks_mod.get(workspace, task.id).status == TaskStatus.BACKLOG

        _, batch = self._reconcile(workspace, task.id)

        assert batch.results[task.id] == "COMPLETED"
        assert tasks_mod.get(workspace, task.id).status == TaskStatus.DONE

    def test_an_in_progress_task_is_marked_DONE(self, workspace):
        from codeframe.core import tasks as tasks_mod

        task = self._task_with_closed_issue(workspace, TaskStatus.IN_PROGRESS)

        self._reconcile(workspace, task.id)

        assert tasks_mod.get(workspace, task.id).status == TaskStatus.DONE

    def test_a_refused_transition_does_not_break_reconciliation(
        self, workspace, monkeypatch
    ):
        """The batch-level record still stands if the row cannot be moved."""
        from codeframe.core import tasks as tasks_mod

        task = self._task_with_closed_issue(workspace, TaskStatus.READY)

        def boom(*args, **kwargs):
            raise RuntimeError("state machine said no")

        monkeypatch.setattr(tasks_mod, "update_status", boom)

        result, batch = self._reconcile(workspace, task.id)

        assert batch.results[task.id] == "COMPLETED"
        assert result.errors == []


class TestWholePathWithStubbedIssuesService:
    """AC4 end-to-end: engine → default fetch → issues service, several ticks.

    Unlike the tests above this does not stub the ``fetch`` callable — it stubs
    ``github_issues_service.get_issue`` itself, so the default fetch, the
    ``asyncio.run`` bridge off the reconciliation thread, and the ``state`` key
    added to ``GitHubIssueDetail`` are all exercised for real.
    """

    def test_ten_ticks_over_three_tasks_stay_bounded(self, monkeypatch):
        calls = []

        async def fake_get_issue(pat, repo, number, *, client=None):
            calls.append((repo, number))
            return {
                "number": number,
                "title": "t",
                "body": "",
                "labels": [],
                "html_url": f"https://github.com/{repo}/issues/{number}",
                "state": "closed" if number == 42 else "open",
            }

        monkeypatch.setattr(
            "codeframe.core.github_issues_service.get_issue", fake_get_issue
        )

        by_id = {
            "linked-closed": make_task(task_id="linked-closed", issue_number=42),
            "linked-open": make_task(
                task_id="linked-open",
                issue_number=43,
                external_url="https://github.com/acme/app/issues/43",
            ),
            "unlinked": make_task(task_id="unlinked", issue_number=None),
        }
        monkeypatch.setattr(
            "codeframe.core.tasks.get", lambda ws, tid: by_id[tid]
        )

        clock = FakeClock()
        engine = ReconciliationEngine(
            workspace=object(), issue_state=GitHubIssueState(pat="tok", now=clock)
        )

        detected = []
        for _ in range(10):
            detected.extend(engine.check_all_active(list(by_id)).changes_detected)
            clock.advance(30)

        # The unlinked task never reaches the service at all.
        assert [c for c in calls if c[1] not in (42, 43)] == []
        # The closed issue is fetched once and never again.
        assert [c for c in calls if c[1] == 42] == [("acme/app", 42)]
        # The open one is re-checked so a later closure is not missed, but at
        # the open-TTL, not once per tick: 10 ticks x 30s / 60s TTL = 5, not 10.
        assert 1 < len([c for c in calls if c[1] == 43]) <= 5

        assert {c.task_id for c in detected} == {"linked-closed"}
        assert detected[0].change_type == "completed"
        assert detected[0].source == "github"
