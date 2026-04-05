"""
Web Lifecycle Test — full Think → Build → Prove loop via browser interaction.

Tests that a user can drive the entire pipeline through the web UI:
upload PRD → generate tasks → launch execution → watch live stream → verify.

Status: STUB — implement after API lifecycle is stable.
Requires: codeframe serve + web-ui dev server running.
Runtime: 15–45 minutes. Cost: ~$0.50–2.00 per run.
"""

import pytest

pytestmark = [pytest.mark.lifecycle, pytest.mark.slow]


@pytest.mark.skip(reason="Web lifecycle test — implement after API lifecycle is stable")
class TestWebLifecycle:
    """Full lifecycle via browser: Playwright drives the web UI end-to-end."""

    def test_user_can_build_project_via_web_ui(self, initialized_workspace, page):
        """
        A user drives the full pipeline through the web UI.

        Plan (Playwright):
        1. Navigate to /
        2. Create workspace or use existing
        3. Go to /prd → upload PRD.md
        4. Go to /tasks → click "Generate Tasks"
        5. Verify tasks appear in kanban board
        6. Go to /execution → click "Run All Ready"
        7. Watch live event stream (SSE) on /execution/[batchId]
        8. Wait for all tasks to reach DONE
        9. Run acceptance checks on generated project
        """
        raise NotImplementedError

    def test_blockers_surface_in_ui(self, initialized_workspace, page):
        """
        If the agent creates a blocker, it appears on /blockers with resolution UI.

        Plan:
        1. Run execution on a task designed to trigger a blocker
        2. Navigate to /blockers
        3. Verify blocker appears with context
        4. Submit answer via UI
        5. Verify task resumes
        """
        raise NotImplementedError
