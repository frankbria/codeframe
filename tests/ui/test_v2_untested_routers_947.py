"""Functional tests for the six v2 routers nothing exercised (#947).

`batches_v2`, `checkpoints_v2`, `git_v2`, `review_v2`, `schedule_v2` and
`templates_v2` — ~1,715 LOC — were referenced by no test other than one
401/not-401 auth smoke line each. That includes state-mutating and destructive
routes (checkpoint restore, git commit, template apply) and the batch
stop/resume/cancel error mapping, which dispatches on

    if "not found" in error_msg.lower():

a string match against a message it does not own. CI green said nothing about
whether any of it worked.

Everything here uses a real workspace, a real git repository and the real core
modules — no mocks — so a test passing means the endpoint actually works. The
one exception is `review_v2`, where `review.review_files` is monkeypatched in
the error-path test only; its happy path runs the real analyzers.

Pattern follows tests/ui/test_v2_routers_integration.py: a fresh FastAPI app
carrying only the routers under test, with `get_v2_workspace` overridden.
"""

import subprocess

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codeframe.core import conductor, tasks
from codeframe.core.state_machine import TaskStatus
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2


def _git(*args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)


@pytest.fixture
def repo(tmp_path):
    """A real git repo with one commit — several routes shell out to git."""
    _git("git", "init", "-q", cwd=tmp_path)
    _git("git", "config", "user.email", "t@t.test", cwd=tmp_path)
    _git("git", "config", "user.name", "T", cwd=tmp_path)
    (tmp_path / "README.md").write_text("# base\n")
    _git("git", "add", "-A", cwd=tmp_path)
    _git("git", "commit", "-qm", "init", cwd=tmp_path)
    return tmp_path


@pytest.fixture
def workspace(repo):
    return create_or_load_workspace(repo)


@pytest.fixture
def client(workspace):
    from codeframe.ui.dependencies import get_v2_workspace
    from codeframe.ui.routers import (
        batches_v2,
        checkpoints_v2,
        git_v2,
        review_v2,
        schedule_v2,
        templates_v2,
    )

    app = FastAPI()
    for mod in (
        batches_v2,
        checkpoints_v2,
        git_v2,
        review_v2,
        schedule_v2,
        templates_v2,
    ):
        app.include_router(mod.router)

    app.dependency_overrides[get_v2_workspace] = lambda: workspace
    return TestClient(app)


# ===========================================================================
# batches_v2 — the "not found" string dispatch
# ===========================================================================


@pytest.fixture
def batch(workspace):
    """A real persisted batch, not executed (dry_run keeps it off the LLM)."""
    task = tasks.create(workspace, title="t", description="")
    return conductor.create_batch(workspace, [task.id], dry_run=True)


class TestBatchesList:
    def test_empty_workspace_lists_nothing(self, client):
        res = client.get("/api/v2/batches")

        assert res.status_code == 200
        assert res.json()["batches"] == []

    def test_a_created_batch_appears(self, client, batch):
        res = client.get("/api/v2/batches")

        assert res.status_code == 200
        assert [b["id"] for b in res.json()["batches"]] == [batch.id]

    def test_get_by_id(self, client, batch):
        res = client.get(f"/api/v2/batches/{batch.id}")

        assert res.status_code == 200
        assert res.json()["id"] == batch.id

    def test_get_unknown_id_is_404(self, client):
        assert client.get("/api/v2/batches/nope").status_code == 404


class TestBatchStopResumeCancelErrorMapping:
    """The handlers distinguish 404 from 400 by string-matching the ValueError
    message. Never executed by a test before — and it is the difference between
    "no such batch" and "batch is in the wrong state"."""

    @pytest.mark.parametrize("action", ["stop", "resume", "cancel"])
    def test_unknown_batch_is_404_not_400(self, client, action):
        res = client.post(f"/api/v2/batches/does-not-exist/{action}")

        assert res.status_code == 404, res.text

    @pytest.mark.parametrize("action", ["stop", "cancel"])
    def test_a_terminal_batch_is_400_not_404(self, client, batch, action):
        """A dry-run batch lands COMPLETED, which is neither stoppable nor
        cancellable. The batch EXISTS, so 404 would be wrong."""
        res = client.post(f"/api/v2/batches/{batch.id}/{action}")

        assert res.status_code == 400, res.text

    def test_resuming_a_completed_batch_is_400(self, client, batch):
        res = client.post(f"/api/v2/batches/{batch.id}/resume")

        assert res.status_code == 400, res.text

    def test_the_two_error_bodies_are_distinguishable(self, client, batch):
        """Same route, both branches, different NOT_FOUND/INVALID_STATE codes —
        the whole point of the dispatch."""
        missing = client.post("/api/v2/batches/nope/stop").json()["detail"]
        wrong_state = client.post(f"/api/v2/batches/{batch.id}/stop").json()["detail"]

        assert missing["code"] != wrong_state["code"]

    def test_resume_of_a_resumable_batch_succeeds(self, client, workspace):
        """Happy path. A CANCELLED batch whose tasks all already resolved has
        nothing to re-run, so resume returns it without touching an LLM."""
        task = tasks.create(workspace, title="t", description="")
        b = conductor.create_batch(workspace, [task.id])
        conductor.cancel_batch(workspace, b.id)

        res = client.post(f"/api/v2/batches/{b.id}/resume")

        assert res.status_code == 200, res.text
        assert res.json()["id"] == b.id


# ===========================================================================
# checkpoints_v2 — including the destructive restore
# ===========================================================================


class TestCheckpointLifecycle:
    def test_create_returns_the_checkpoint(self, client):
        res = client.post("/api/v2/checkpoints", json={"name": "before"})

        assert res.status_code == 200, res.text
        assert res.json()["name"] == "before"

    def test_it_then_appears_in_the_list_and_by_id(self, client):
        cid = client.post("/api/v2/checkpoints", json={"name": "c1"}).json()["id"]

        listed = client.get("/api/v2/checkpoints")
        one = client.get(f"/api/v2/checkpoints/{cid}")

        assert cid in [c["id"] for c in listed.json()["checkpoints"]]
        assert one.status_code == 200
        assert one.json()["id"] == cid

    def test_get_unknown_checkpoint_is_404(self, client):
        assert client.get("/api/v2/checkpoints/nope").status_code == 404


class TestCheckpointRestore:
    """Destructive: it rewrites task statuses. Untested until now."""

    def test_restore_puts_the_task_status_back(self, client, workspace):
        task = tasks.create(workspace, title="t", description="")
        tasks.update_status(workspace, task.id, TaskStatus.READY)
        cid = client.post("/api/v2/checkpoints", json={"name": "at-ready"}).json()["id"]
        tasks.update_status(workspace, task.id, TaskStatus.IN_PROGRESS)

        res = client.post(f"/api/v2/checkpoints/{cid}/restore")

        assert res.status_code == 200, res.text
        assert res.json()["success"] is True
        assert tasks.get(workspace, task.id).status == TaskStatus.READY, (
            "the endpoint reported success without restoring anything"
        )

    def test_restoring_an_unknown_checkpoint_is_404(self, client):
        res = client.post("/api/v2/checkpoints/nope/restore")

        assert res.status_code == 404, res.text

    def test_a_failed_restore_changes_nothing(self, client, workspace):
        task = tasks.create(workspace, title="t", description="")
        tasks.update_status(workspace, task.id, TaskStatus.READY)

        client.post("/api/v2/checkpoints/nope/restore")

        assert tasks.get(workspace, task.id).status == TaskStatus.READY


class TestCheckpointDelete:
    def test_delete_removes_it(self, client):
        cid = client.post("/api/v2/checkpoints", json={"name": "d"}).json()["id"]

        res = client.delete(f"/api/v2/checkpoints/{cid}")

        assert res.status_code == 200, res.text
        assert client.get(f"/api/v2/checkpoints/{cid}").status_code == 404

    def test_deleting_an_unknown_checkpoint_is_404(self, client):
        assert client.delete("/api/v2/checkpoints/nope").status_code == 404


class TestCheckpointDiff:
    def test_two_checkpoints_diff(self, client, workspace):
        a = client.post("/api/v2/checkpoints", json={"name": "a"}).json()["id"]
        tasks.create(workspace, title="added-between", description="")
        b = client.post("/api/v2/checkpoints", json={"name": "b"}).json()["id"]

        res = client.get(f"/api/v2/checkpoints/{a}/diff/{b}")

        assert res.status_code == 200, res.text

    def test_diff_against_an_unknown_checkpoint_is_404(self, client):
        a = client.post("/api/v2/checkpoints", json={"name": "a"}).json()["id"]

        assert client.get(f"/api/v2/checkpoints/{a}/diff/nope").status_code == 404


# ===========================================================================
# git_v2 — including the commit that writes to the user's repository
# ===========================================================================


class TestGitReadEndpoints:
    def test_status_reports_the_branch_and_a_new_file(self, client, repo):
        (repo / "new.py").write_text("x = 1\n")

        res = client.get("/api/v2/git/status")

        assert res.status_code == 200, res.text
        body = res.json()
        assert body["current_branch"]
        assert "new.py" in body["untracked_files"]

    def test_commits_lists_the_initial_commit(self, client):
        res = client.get("/api/v2/git/commits")

        assert res.status_code == 200, res.text
        # CommitListResponse carries `commits` only — no `total`, unlike the
        # sibling list endpoints. Asserting the shape so a later "consistency"
        # edit is a deliberate change rather than a silent client break.
        assert [c["message"] for c in res.json()["commits"]] == ["init"]

    def test_branch_matches_git(self, client, repo):
        expected = _git("git", "branch", "--show-current", cwd=repo).stdout.strip()

        assert client.get("/api/v2/git/branch").json()["branch"] == expected

    def test_clean_flips_when_the_tree_is_dirty(self, client, repo):
        assert client.get("/api/v2/git/clean").json()["is_clean"] is True

        (repo / "README.md").write_text("# edited\n")

        assert client.get("/api/v2/git/clean").json()["is_clean"] is False

    def test_diff_contains_the_edit(self, client, repo):
        (repo / "README.md").write_text("# edited\n")

        res = client.get("/api/v2/git/diff")

        assert res.status_code == 200, res.text
        assert "edited" in res.json()["diff"]


class TestGitCommit:
    """Writes to the user's repository. Untested until now."""

    def test_a_commit_actually_lands_in_git_history(self, client, repo):
        (repo / "feature.py").write_text("print('hi')\n")

        res = client.post(
            "/api/v2/git/commit",
            json={"files": ["feature.py"], "message": "add feature"},
        )

        assert res.status_code == 201, res.text
        assert res.json()["files_changed"] == 1
        log = _git("git", "log", "-1", "--name-only", "--pretty=%s", cwd=repo).stdout
        assert "add feature" in log
        assert "feature.py" in log

    def test_it_commits_only_the_requested_file(self, client, repo):
        (repo / "wanted.py").write_text("a = 1\n")
        (repo / "unwanted.py").write_text("b = 2\n")
        _git("git", "add", "unwanted.py", cwd=repo)

        client.post(
            "/api/v2/git/commit",
            json={"files": ["wanted.py"], "message": "only wanted"},
        )

        names = _git("git", "show", "--name-only", "--pretty=", "HEAD", cwd=repo).stdout
        assert "wanted.py" in names
        assert "unwanted.py" not in names

    def test_committing_a_path_that_does_not_exist_is_400(self, client):
        res = client.post(
            "/api/v2/git/commit",
            json={"files": ["ghost.py"], "message": "nothing"},
        )

        assert res.status_code == 400, res.text

    def test_a_failed_commit_leaves_history_untouched(self, client, repo):
        before = _git("git", "rev-parse", "HEAD", cwd=repo).stdout

        client.post("/api/v2/git/commit", json={"files": ["ghost.py"], "message": "x"})

        assert _git("git", "rev-parse", "HEAD", cwd=repo).stdout == before


# ===========================================================================
# review_v2
# ===========================================================================


class TestReviewFiles:
    def test_reviewing_a_real_file_returns_a_score(self, client, repo):
        (repo / "sample.py").write_text("def f():\n    return 1\n")

        res = client.post("/api/v2/review/files", json={"files": ["sample.py"]})

        assert res.status_code == 200, res.text
        body = res.json()
        assert "overall_score" in body
        assert isinstance(body["findings"], list)

    def test_a_missing_file_is_reported_as_skipped_not_a_crash(self, client):
        res = client.post("/api/v2/review/files", json={"files": ["ghost.py"]})

        assert res.status_code == 200, res.text
        assert res.json()["files_skipped"], "a nonexistent file vanished silently"

    def test_the_summary_endpoint_agrees_with_the_full_one(self, client, repo):
        (repo / "sample.py").write_text("def f():\n    return 1\n")
        payload = {"files": ["sample.py"]}

        full = client.post("/api/v2/review/files", json=payload).json()
        summary = client.post("/api/v2/review/files/summary", json=payload).json()

        assert summary["overall_score"] == full["overall_score"]
        assert summary["total_findings"] == len(full["findings"])

    def test_an_unknown_task_id_is_accepted_silently(self, client, repo):
        """Documenting, not endorsing. `review.review_task` uses `task_id` for a
        log line and nothing else — it never loads the task — so the endpoint
        looks task-scoped and is not. A caller passing a stale or wrong id gets
        a confident 200 about whatever files it also sent. Filed separately
        rather than changed under a test-only issue."""
        (repo / "sample.py").write_text("x = 1\n")

        res = client.post(
            "/api/v2/review/task",
            json={"task_id": "no-such-task", "files_modified": ["sample.py"]},
        )

        assert res.status_code == 200, res.text

    def test_review_task_requires_the_file_list(self, client):
        """files_modified is required with min_length=1, so the endpoint cannot
        be called with a task id alone — worth pinning, since the name suggests
        it would resolve the files itself."""
        res = client.post("/api/v2/review/task", json={"task_id": "nope"})

        assert res.status_code == 422

    def test_reviewing_a_real_tasks_files_succeeds(self, client, repo, workspace):
        (repo / "sample.py").write_text("def f():\n    return 1\n")
        task = tasks.create(workspace, title="t", description="")

        res = client.post(
            "/api/v2/review/task",
            json={"task_id": task.id, "files_modified": ["sample.py"]},
        )

        assert res.status_code == 200, res.text
        assert "overall_score" in res.json()

    def test_an_analyzer_crash_becomes_a_500_not_a_traceback(
        self, client, monkeypatch
    ):
        """The only monkeypatch in this module: there is no input that makes the
        real analyzers raise, and the 500 branch is otherwise unreachable."""
        from codeframe.core import review as review_core

        def boom(*a, **kw):
            raise RuntimeError("analyzer exploded")

        monkeypatch.setattr(review_core, "review_files", boom)

        res = client.post("/api/v2/review/files", json={"files": ["x.py"]})

        assert res.status_code == 500


class TestReviewDiffAndPatch:
    def test_diff_reports_per_file_stats(self, client, repo):
        (repo / "README.md").write_text("# one\n# two\n")

        res = client.get("/api/v2/review/diff")

        assert res.status_code == 200, res.text
        body = res.json()
        assert body["files_changed"] == 1
        assert [f["path"] for f in body["changed_files"]] == ["README.md"]

    def test_patch_filename_is_derived_from_the_branch(self, client, repo):
        (repo / "README.md").write_text("# changed\n")
        branch = _git("git", "branch", "--show-current", cwd=repo).stdout.strip()

        res = client.get("/api/v2/review/patch")

        assert res.status_code == 200, res.text
        assert res.json()["filename"] == f"{branch.replace('/', '-')}.patch"

    def test_a_generated_commit_message_is_not_empty(self, client, repo):
        (repo / "README.md").write_text("# changed\n")

        res = client.post("/api/v2/review/commit-message")

        assert res.status_code == 200, res.text
        assert res.json()["message"].strip()


# ===========================================================================
# schedule_v2
# ===========================================================================


class TestSchedule:
    def test_an_empty_workspace_is_a_404(self, client):
        """Documenting, not endorsing. `schedule.get_schedule` raises
        ValueError("No tasks found in workspace") and the handler maps every
        ValueError to 404 — so a brand-new workspace gets "Schedule not found"
        for what is really an empty, perfectly valid schedule. Pinned here so
        the behaviour is at least known; filed separately rather than changed
        under a test-only issue."""
        res = client.get("/api/v2/schedule")

        assert res.status_code == 404
        assert res.json()["detail"]["code"] == "NOT_FOUND"

    def test_tasks_are_assigned(self, client, workspace):
        for i in range(3):
            tasks.create(workspace, title=f"t{i}", description="", estimated_hours=2.0)

        res = client.get("/api/v2/schedule")

        assert res.status_code == 200, res.text
        assert len(res.json()["task_assignments"]) == 3

    def test_more_agents_do_not_lengthen_the_schedule(self, client, workspace):
        for i in range(4):
            tasks.create(workspace, title=f"t{i}", description="", estimated_hours=2.0)

        one = client.get("/api/v2/schedule", params={"agents": 1}).json()
        four = client.get("/api/v2/schedule", params={"agents": 4}).json()

        assert four["total_duration"] <= one["total_duration"]

    def test_agents_is_validated(self, client):
        assert client.get("/api/v2/schedule", params={"agents": 0}).status_code == 422
        assert client.get("/api/v2/schedule", params={"agents": 99}).status_code == 422

    def test_predict_returns_a_date_and_a_window(self, client, workspace):
        tasks.create(workspace, title="t", description="", estimated_hours=8.0)

        res = client.get("/api/v2/schedule/predict")

        assert res.status_code == 200, res.text
        body = res.json()
        assert body["predicted_date"]
        assert set(body["confidence_interval"]) == {"early", "late"}

    def test_hours_per_day_is_validated(self, client):
        res = client.get("/api/v2/schedule/predict", params={"hours_per_day": 0})

        assert res.status_code == 422

    def test_bottlenecks_returns_a_list(self, client, workspace):
        tasks.create(workspace, title="t", description="", estimated_hours=40.0)

        res = client.get("/api/v2/schedule/bottlenecks")

        assert res.status_code == 200, res.text
        assert isinstance(res.json(), list)


# ===========================================================================
# templates_v2 — including apply, which creates tasks
# ===========================================================================


class TestTemplateBrowsing:
    def test_list_returns_the_builtins(self, client):
        res = client.get("/api/v2/templates")

        assert res.status_code == 200, res.text
        assert res.json(), "no built-in templates were returned"

    def test_category_filter_narrows_the_list(self, client):
        every = client.get("/api/v2/templates").json()
        backend = client.get("/api/v2/templates", params={"category": "backend"}).json()

        assert backend
        assert len(backend) < len(every)
        assert {t["category"] for t in backend} == {"backend"}

    def test_categories_endpoint(self, client):
        res = client.get("/api/v2/templates/categories")

        assert res.status_code == 200, res.text
        assert "backend" in res.json()["categories"]

    def test_get_one_by_id(self, client):
        res = client.get("/api/v2/templates/api-endpoint")

        assert res.status_code == 200, res.text
        assert res.json()["id"] == "api-endpoint"

    def test_unknown_template_is_404(self, client):
        assert client.get("/api/v2/templates/nope").status_code == 404


class TestTemplateApply:
    """Creates tasks in the workspace. Untested until now."""

    def test_applying_a_template_creates_the_tasks_it_reports(self, client, workspace):
        res = client.post("/api/v2/templates/apply", json={"template_id": "api-endpoint"})

        assert res.status_code == 200, res.text
        body = res.json()
        assert body["tasks_created"] == len(body["task_ids"])
        assert body["tasks_created"] > 0
        for task_id in body["task_ids"]:
            assert tasks.get(workspace, task_id) is not None, (
                "the response listed a task id that does not exist"
            )

    def test_applying_an_unknown_template_is_404(self, client):
        res = client.post("/api/v2/templates/apply", json={"template_id": "nope"})

        assert res.status_code == 404, res.text

    def test_a_failed_apply_creates_no_tasks(self, client, workspace):
        client.post("/api/v2/templates/apply", json={"template_id": "nope"})

        assert tasks.list_tasks(workspace) == []

    def test_issue_number_is_a_string_not_an_int(self, client):
        """It feeds the template's task numbering, NOT `github_issue_number` —
        despite the name. Typed `str`, so the integer a caller would naturally
        send is rejected. Pinning both halves so the coupling is visible."""
        assert (
            client.post(
                "/api/v2/templates/apply",
                json={"template_id": "api-endpoint", "issue_number": 42},
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/v2/templates/apply",
                json={"template_id": "api-endpoint", "issue_number": "42"},
            ).status_code
            == 200
        )

    def test_apply_does_not_set_github_traceability(self, client, workspace):
        """The negative half of the above: nothing links these tasks to a
        GitHub issue, so the import path's dedupe/auto-close cannot see them."""
        res = client.post(
            "/api/v2/templates/apply",
            json={"template_id": "api-endpoint", "issue_number": "42"},
        )

        created = [tasks.get(workspace, tid) for tid in res.json()["task_ids"]]
        assert all(t.github_issue_number is None for t in created)

    def test_template_dependencies_are_wired_to_real_task_ids(self, client, workspace):
        """apply_template maps 0-based depends_on_indices onto created ids. A
        mis-mapping would produce dangling references no other test would see."""
        res = client.post("/api/v2/templates/apply", json={"template_id": "api-endpoint"})
        created_ids = set(res.json()["task_ids"])

        for tid in created_ids:
            for dep in tasks.get(workspace, tid).depends_on:
                assert dep in created_ids, f"task {tid} depends on unknown {dep}"


# ===========================================================================
# The generic 500 handlers
# ===========================================================================


class TestUnexpectedCoreFailuresBecome500s:
    """Each router wraps its core call in `except Exception -> 500`. There is no
    input that reaches those branches — that is the point of them — so this is
    the one place the module substitutes a raising core function. Without it a
    handler could re-raise, or return a 200 with a half-built body, and nothing
    would notice.

    Kept as one table rather than a test per route so adding a route to a
    router is a one-line addition here.
    """

    CASES = [
        ("codeframe.core.checkpoints", "create", "POST", "/api/v2/checkpoints", {"name": "x"}),
        ("codeframe.core.git", "get_status", "GET", "/api/v2/git/status", None),
        ("codeframe.core.git", "list_commits", "GET", "/api/v2/git/commits", None),
        ("codeframe.core.git", "get_diff", "GET", "/api/v2/git/diff", None),
        ("codeframe.core.git", "get_current_branch", "GET", "/api/v2/git/branch", None),
        ("codeframe.core.git", "is_clean", "GET", "/api/v2/git/clean", None),
        ("codeframe.core.git", "get_diff_stats", "GET", "/api/v2/review/diff", None),
        ("codeframe.core.git", "get_patch", "GET", "/api/v2/review/patch", None),
        (
            "codeframe.core.git",
            "generate_commit_message",
            "POST",
            "/api/v2/review/commit-message",
            None,
        ),
        ("codeframe.core.schedule", "get_schedule", "GET", "/api/v2/schedule", None),
        (
            "codeframe.core.schedule",
            "predict_completion",
            "GET",
            "/api/v2/schedule/predict",
            None,
        ),
        (
            "codeframe.core.schedule",
            "get_bottlenecks",
            "GET",
            "/api/v2/schedule/bottlenecks",
            None,
        ),
        ("codeframe.core.templates", "list_templates", "GET", "/api/v2/templates", None),
        (
            "codeframe.core.templates",
            "get_categories",
            "GET",
            "/api/v2/templates/categories",
            None,
        ),
        (
            "codeframe.core.templates",
            "get_template",
            "GET",
            "/api/v2/templates/api-endpoint",
            None,
        ),
        (
            "codeframe.core.templates",
            "apply_template",
            "POST",
            "/api/v2/templates/apply",
            {"template_id": "api-endpoint"},
        ),
    ]

    @pytest.mark.parametrize(
        "module_path,func,method,url,body",
        CASES,
        ids=[f"{c[3]}::{c[1]}" for c in CASES],
    )
    def test_a_raising_core_call_is_a_500(
        self, client, monkeypatch, module_path, func, method, url, body
    ):
        import importlib

        module = importlib.import_module(module_path)

        def boom(*a, **kw):
            raise RuntimeError("core exploded")

        monkeypatch.setattr(module, func, boom)

        res = client.request(method, url, json=body)

        assert res.status_code == 500, f"{method} {url} -> {res.status_code} {res.text}"

    def test_the_500_body_never_leaks_the_exception_text_from_git(
        self, client, monkeypatch
    ):
        """git_v2 routes go through `internal_error()` (#934), which replaces
        the message with a correlation id. Host paths and git internals used to
        reach any authenticated tenant."""
        from codeframe.core import git as git_core

        def boom(*a, **kw):
            raise RuntimeError("/home/someone/secret/path exploded")

        monkeypatch.setattr(git_core, "get_status", boom)

        body = client.get("/api/v2/git/status").text

        assert "/home/someone/secret/path" not in body

    @pytest.mark.parametrize(
        "module_path,func,url",
        [
            ("codeframe.core.conductor", "list_batches", "/api/v2/batches"),
            ("codeframe.core.checkpoints", "list_all", "/api/v2/checkpoints"),
        ],
    )
    def test_the_two_unguarded_list_routes_still_500(
        self, workspace, monkeypatch, module_path, func, url
    ):
        """These two have NO try/except at all — unlike every sibling route in
        the same files. The ASGI server turns the escape into a 500, so the
        client-visible result is the same, but nothing is logged with a
        correlation id and the message is not scrubbed. Asserted with
        raise_server_exceptions=False, which is what a real server does.
        """
        import importlib

        from codeframe.ui.dependencies import get_v2_workspace
        from codeframe.ui.routers import batches_v2, checkpoints_v2

        module = importlib.import_module(module_path)

        def boom(*a, **kw):
            raise RuntimeError("core exploded")

        monkeypatch.setattr(module, func, boom)

        app = FastAPI()
        app.include_router(batches_v2.router)
        app.include_router(checkpoints_v2.router)
        app.dependency_overrides[get_v2_workspace] = lambda: workspace

        res = TestClient(app, raise_server_exceptions=False).get(url)

        assert res.status_code == 500
