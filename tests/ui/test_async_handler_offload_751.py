"""Regression guard for #751: sync SQLite work must not run on the event loop.

The task/costs read + CRUD handlers do blocking SQLite work directly. Declaring
them ``async def`` pins that disk I/O to the event-loop thread, serializing every
concurrent request behind it. The fix (per the issue's acceptance criteria) is to
declare them plain ``def`` so FastAPI dispatches them to its anyio threadpool.

These tests assert the offload structurally — a handler that regresses back to
``async def`` (re-blocking the loop) fails here. Behavior is covered by the
existing router tests; this file only guards *where* the work runs.
"""

import asyncio

import pytest
from fastapi.routing import APIRoute

from codeframe.ui.routers import costs_v2, tasks_v2

pytestmark = pytest.mark.v2


def _endpoints_by_name(router):
    """Map handler ``__name__`` -> route endpoint for a router's APIRoutes.

    ``functools.wraps`` (used by slowapi's rate-limit wrapper) preserves
    ``__name__``, so this works whether or not rate limiting is enabled.
    """
    return {
        route.endpoint.__name__: route.endpoint
        for route in router.routes
        if isinstance(route, APIRoute)
    }


# Handlers whose body is purely synchronous SQLite work — must be offloaded.
OFFLOADED_TASK_HANDLERS = [
    "list_tasks",
    "get_task",
    "update_task",
    "delete_task",
    "get_assignment_status",
    "get_task_run",
]
OFFLOADED_COST_HANDLERS = [
    "get_costs_summary",
    "get_costs_by_task",
    "get_costs_by_agent_endpoint",
]

# Handlers intentionally left ``async``: they orchestrate the conductor/runtime,
# spawn worker threads, use BackgroundTasks, or return a StreamingResponse — none
# are the "blocking SQLite serializes requests" case this issue targets.
STREAMING_OR_ORCHESTRATION_HANDLERS = [
    "stream_task_output_lines",
    "stream_task_events",
    "start_single_task",
]


@pytest.mark.parametrize("name", OFFLOADED_TASK_HANDLERS)
def test_task_db_handlers_are_offloaded(name):
    endpoints = _endpoints_by_name(tasks_v2.router)
    assert name in endpoints, f"{name} route missing from tasks_v2 router"
    assert not asyncio.iscoroutinefunction(endpoints[name]), (
        f"{name} is async — blocking SQLite would run on the event loop. "
        "Declare it plain `def` so FastAPI offloads it to the threadpool (#751)."
    )


@pytest.mark.parametrize("name", OFFLOADED_COST_HANDLERS)
def test_cost_handlers_are_offloaded(name):
    endpoints = _endpoints_by_name(costs_v2.router)
    assert name in endpoints, f"{name} route missing from costs_v2 router"
    assert not asyncio.iscoroutinefunction(endpoints[name]), (
        f"{name} is async — blocking SQLite would run on the event loop. "
        "Declare it plain `def` so FastAPI offloads it to the threadpool (#751)."
    )


@pytest.mark.parametrize("name", STREAMING_OR_ORCHESTRATION_HANDLERS)
def test_streaming_and_orchestration_handlers_stay_async(name):
    endpoints = _endpoints_by_name(tasks_v2.router)
    assert name in endpoints, f"{name} route missing from tasks_v2 router"
    assert asyncio.iscoroutinefunction(endpoints[name]), (
        f"{name} must stay async (it streams or orchestrates); converting it to "
        "`def` is out of scope for #751 and risks breaking its event-loop usage."
    )
