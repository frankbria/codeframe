"""Silent truncation at list limits (#1294).

`list_tasks` defaulted to 100 rows and every caller that relied on the default
wanted all of them; `events.list_recent(since_id=...)` returned the *newest* N
rows after the cursor, so a poller skipped the oldest ones.
"""

import itertools
from pathlib import Path

import pytest
from typer.testing import CliRunner

from codeframe.cli.app import app
from codeframe.core import events, prd, tasks
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2

MANY = 150


@pytest.fixture
def ws(tmp_path: Path):
    return create_or_load_workspace(tmp_path)


def _make_tasks(ws, n=MANY):
    return [tasks.create(ws, title=f"T{i}") for i in range(n)]


def test_list_tasks_returns_every_task_by_default(ws):
    _make_tasks(ws)
    assert len(tasks.list_tasks(ws)) == MANY


def test_an_explicit_limit_still_caps(ws):
    _make_tasks(ws)
    assert len(tasks.list_tasks(ws, limit=100)) == 100


def test_get_dependents_sees_past_the_hundredth_task(ws):
    created = _make_tasks(ws)
    dep = tasks.create(ws, title="late", depends_on=[created[0].id])
    assert dep.id in {t.id for t in tasks.get_dependents(ws, created[0].id)}


def test_overwrite_removes_every_old_task(ws):
    prd.store(ws, content="# Demo\n\n- Build a thing\n", title="Demo")
    old = {t.id for t in _make_tasks(ws)}

    result = CliRunner().invoke(
        app, ["tasks", "generate", "--overwrite", "--no-llm", "-w", str(ws.repo_path)]
    )

    assert result.exit_code == 0, result.output
    survivors = old & {t.id for t in tasks.list_tasks(ws)}
    assert not survivors, f"{len(survivors)} stale tasks survived --overwrite"


def test_tui_dashboard_counts_every_task(ws):
    from codeframe.tui.data_service import load_dashboard_data

    _make_tasks(ws)
    data = load_dashboard_data(ws)
    assert len(data.tasks) == MANY
    assert sum(data.task_counts.values()) == MANY


def _emit(ws, n):
    return [
        events.emit_for_workspace(ws, "test.event", {"i": i}, print_event=False).id
        for i in range(n)
    ]


def test_list_recent_since_id_pages_forward_from_the_cursor(ws):
    ids = _emit(ws, 70)
    page = events.list_recent(ws, limit=50, since_id=ids[0] - 1)
    # The 50 oldest after the cursor, still newest-first like every other page.
    assert [e.id for e in page] == list(reversed(ids[:50]))


def test_tail_yields_every_event_in_order_when_many_arrive_between_polls(ws, monkeypatch):
    ids = _emit(ws, 70)
    polls = itertools.count()

    def bounded_sleep(_seconds):
        # tail() polls forever; a skipped event would otherwise hang the test.
        if next(polls) > 5:
            raise TimeoutError("tail stopped yielding")

    monkeypatch.setattr("time.sleep", bounded_sleep)
    got = []
    with pytest.raises(TimeoutError):
        for event in events.tail(ws, since_id=ids[0] - 1):
            got.append(event.id)
    assert got == ids
