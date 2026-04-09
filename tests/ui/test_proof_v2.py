"""Integration tests for proof_v2 router (PROOF9 REST API).

Verifies that proof_v2 router:
1. Properly delegates to core/proof/* modules
2. Returns correct HTTP status codes and response shapes
3. Handles invalid inputs with structured errors
4. Follows v2 API patterns (workspace-based, standard response format)

Tests use FastAPI TestClient with dependency overrides — no server required.
"""

import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Mark all tests in this module as v2
pytestmark = pytest.mark.v2


@pytest.fixture
def test_workspace():
    """Create a temporary workspace for testing."""
    temp_dir = Path(tempfile.mkdtemp())
    workspace_path = temp_dir / "test_workspace"
    workspace_path.mkdir(parents=True, exist_ok=True)

    from codeframe.core.workspace import create_or_load_workspace

    workspace = create_or_load_workspace(workspace_path)

    yield workspace

    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def test_client(test_workspace):
    """Create a FastAPI TestClient with proof_v2 router and workspace override."""
    from codeframe.ui.routers import proof_v2
    from codeframe.ui.dependencies import get_v2_workspace

    app = FastAPI()
    app.include_router(proof_v2.router)

    def get_test_workspace():
        return test_workspace

    app.dependency_overrides[get_v2_workspace] = get_test_workspace

    client = TestClient(app)
    client.workspace = test_workspace
    return client


# ============================================================================
# POST /api/v2/proof/requirements — capture requirement
# ============================================================================


class TestCaptureRequirement:
    """Tests for POST /api/v2/proof/requirements."""

    def _valid_body(self, **overrides):
        base = {
            "title": "Login fails silently on bad token",
            "description": "Auth logic bug: token expiry not checked before redirect",
            "where": "codeframe/auth/dependencies.py",
            "severity": "high",
            "source": "production",
        }
        base.update(overrides)
        return base

    def test_capture_returns_201(self, test_client):
        """Capture requirement returns 201 on valid input."""
        response = test_client.post(
            "/api/v2/proof/requirements",
            json=self._valid_body(),
        )
        assert response.status_code == 201

    def test_capture_returns_requirement_id(self, test_client):
        """Captured requirement has REQ-#### ID."""
        response = test_client.post(
            "/api/v2/proof/requirements",
            json=self._valid_body(),
        )
        data = response.json()
        assert data["id"].startswith("REQ-")

    def test_capture_response_shape(self, test_client):
        """Response includes all required fields."""
        response = test_client.post(
            "/api/v2/proof/requirements",
            json=self._valid_body(),
        )
        data = response.json()
        for field in ["id", "title", "description", "severity", "source", "status",
                      "obligations", "evidence_rules", "created_at", "stubs_count"]:
            assert field in data, f"Missing field: {field}"

    def test_capture_with_optional_fields(self, test_client):
        """Optional fields (created_by, source_issue) are accepted."""
        body = self._valid_body(
            created_by="ci-bot",
            source_issue="GH-123",
        )
        response = test_client.post("/api/v2/proof/requirements", json=body)
        assert response.status_code == 201
        data = response.json()
        assert data["created_by"] == "ci-bot"
        assert data["source_issue"] == "GH-123"

    def test_capture_status_defaults_to_open(self, test_client):
        """Newly captured requirement has status 'open'."""
        response = test_client.post(
            "/api/v2/proof/requirements",
            json=self._valid_body(),
        )
        assert response.json()["status"] == "open"

    def test_capture_missing_title_returns_422(self, test_client):
        """Missing required field returns 422."""
        body = self._valid_body()
        del body["title"]
        response = test_client.post("/api/v2/proof/requirements", json=body)
        assert response.status_code == 422

    def test_capture_invalid_severity_returns_422(self, test_client):
        """Invalid severity enum returns 422."""
        response = test_client.post(
            "/api/v2/proof/requirements",
            json=self._valid_body(severity="extreme"),
        )
        assert response.status_code == 422

    def test_capture_invalid_source_returns_422(self, test_client):
        """Invalid source enum returns 422."""
        response = test_client.post(
            "/api/v2/proof/requirements",
            json=self._valid_body(source="unknown"),
        )
        assert response.status_code == 422

    def test_capture_persists_to_core(self, test_client):
        """Captured requirement is retrievable via core ledger."""
        from codeframe.core.proof.ledger import list_requirements

        response = test_client.post(
            "/api/v2/proof/requirements",
            json=self._valid_body(),
        )
        req_id = response.json()["id"]
        reqs = list_requirements(test_client.workspace)
        assert any(r.id == req_id for r in reqs)


# ============================================================================
# GET /api/v2/proof/requirements — list requirements
# ============================================================================


class TestListRequirements:
    """Tests for GET /api/v2/proof/requirements."""

    def _capture(self, test_client, **overrides):
        body = {
            "title": "Test requirement",
            "description": "A test bug",
            "where": "core/tasks.py",
            "severity": "medium",
            "source": "qa",
        }
        body.update(overrides)
        return test_client.post("/api/v2/proof/requirements", json=body)

    def test_list_empty(self, test_client):
        """Returns empty list when no requirements exist."""
        response = test_client.get("/api/v2/proof/requirements")
        assert response.status_code == 200
        data = response.json()
        assert data["requirements"] == []
        assert data["total"] == 0
        assert "by_status" in data

    def test_list_returns_captured_requirements(self, test_client):
        """Returns requirements after capture."""
        self._capture(test_client)
        response = test_client.get("/api/v2/proof/requirements")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["requirements"]) == 1

    def test_list_filter_by_valid_status(self, test_client):
        """?status=open returns only open requirements."""
        self._capture(test_client)
        response = test_client.get("/api/v2/proof/requirements?status=open")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        for req in data["requirements"]:
            assert req["status"] == "open"

    def test_list_filter_by_invalid_status(self, test_client):
        """?status=invalid returns 400."""
        response = test_client.get("/api/v2/proof/requirements?status=invalid")
        assert response.status_code == 400
        detail = response.json()["detail"]
        assert "code" in detail

    def test_list_by_status_counts_all_statuses(self, test_client):
        """by_status dict includes all known statuses."""
        response = test_client.get("/api/v2/proof/requirements")
        data = response.json()
        assert "open" in data["by_status"]


# ============================================================================
# GET /api/v2/proof/requirements/{req_id} — get single requirement
# ============================================================================


class TestGetRequirement:
    """Tests for GET /api/v2/proof/requirements/{req_id}."""

    def _capture(self, test_client):
        return test_client.post(
            "/api/v2/proof/requirements",
            json={
                "title": "Get test",
                "description": "Testing get endpoint",
                "where": "core/tasks.py",
                "severity": "low",
                "source": "dogfooding",
            },
        )

    def test_get_existing_requirement(self, test_client):
        """Returns requirement by ID."""
        req_id = self._capture(test_client).json()["id"]
        response = test_client.get(f"/api/v2/proof/requirements/{req_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == req_id
        assert data["title"] == "Get test"

    def test_get_nonexistent_returns_404(self, test_client):
        """Returns 404 for unknown ID."""
        response = test_client.get("/api/v2/proof/requirements/REQ-9999")
        assert response.status_code == 404
        detail = response.json()["detail"]
        assert "code" in detail

    def test_get_returns_full_shape(self, test_client):
        """GET response includes obligations and evidence_rules."""
        req_id = self._capture(test_client).json()["id"]
        response = test_client.get(f"/api/v2/proof/requirements/{req_id}")
        data = response.json()
        assert "obligations" in data
        assert "evidence_rules" in data
        assert isinstance(data["obligations"], list)


# ============================================================================
# POST /api/v2/proof/run — run proof obligations
# ============================================================================


class TestRunProof:
    """Tests for POST /api/v2/proof/run."""

    def test_run_empty_returns_success(self, test_client):
        """Run with no requirements returns success with empty results."""
        response = test_client.post("/api/v2/proof/run", json={})
        assert response.status_code == 200
        data = response.json()
        assert "success" in data
        assert "run_id" in data
        assert "results" in data

    def test_run_returns_run_id(self, test_client):
        """Response includes a run_id."""
        response = test_client.post("/api/v2/proof/run", json={})
        assert response.json()["run_id"] is not None

    def test_run_full_flag_accepted(self, test_client):
        """full=True is accepted."""
        response = test_client.post("/api/v2/proof/run", json={"full": True})
        assert response.status_code == 200

    def test_run_with_gate_filter(self, test_client):
        """gate filter is accepted."""
        response = test_client.post("/api/v2/proof/run", json={"gate": "unit"})
        assert response.status_code == 200

    def test_run_invalid_gate_returns_422(self, test_client):
        """Invalid gate enum returns 422."""
        response = test_client.post("/api/v2/proof/run", json={"gate": "not_a_gate"})
        assert response.status_code == 422

    def test_run_results_shape(self, test_client):
        """results is a dict mapping req_id to list of gate results."""
        # Capture a requirement first so there's something to run
        test_client.post(
            "/api/v2/proof/requirements",
            json={
                "title": "Run test req",
                "description": "A logic bug for run test",
                "where": "core/tasks.py",
                "severity": "medium",
                "source": "qa",
            },
        )
        response = test_client.post("/api/v2/proof/run", json={"full": True})
        data = response.json()
        assert isinstance(data["results"], dict)


# ============================================================================
# GET /api/v2/proof/runs/{run_id} — poll run status
# ============================================================================


class TestGetRunStatus:
    """Tests for GET /api/v2/proof/runs/{run_id}."""

    def setup_method(self):
        """Reset the run cache so tests don't share state."""
        from codeframe.ui.routers import proof_v2
        proof_v2._run_cache.clear()

    def test_get_run_after_post_returns_200(self, test_client):
        """GET /runs/{run_id} returns 200 after a completed POST /run."""
        post_resp = test_client.post("/api/v2/proof/run", json={})
        assert post_resp.status_code == 200
        run_id = post_resp.json()["run_id"]

        response = test_client.get(f"/api/v2/proof/runs/{run_id}")
        assert response.status_code == 200

    def test_get_run_response_shape(self, test_client):
        """RunStatusResponse has required fields."""
        post_resp = test_client.post("/api/v2/proof/run", json={})
        run_id = post_resp.json()["run_id"]

        data = test_client.get(f"/api/v2/proof/runs/{run_id}").json()
        assert data["run_id"] == run_id
        assert data["status"] == "complete"
        assert isinstance(data["results"], dict)
        assert isinstance(data["passed"], bool)
        assert isinstance(data["message"], str)

    def test_get_unknown_run_returns_404(self, test_client):
        """Unknown run_id returns 404."""
        response = test_client.get("/api/v2/proof/runs/does-not-exist")
        assert response.status_code == 404

    def test_get_run_results_match_post(self, test_client):
        """GET run results match the original POST results."""
        post_resp = test_client.post("/api/v2/proof/run", json={"full": True})
        post_data = post_resp.json()
        run_id = post_data["run_id"]

        get_data = test_client.get(f"/api/v2/proof/runs/{run_id}").json()
        assert get_data["results"] == post_data["results"]


# ============================================================================
# POST /api/v2/proof/requirements/{req_id}/waive — waive requirement
# ============================================================================


class TestWaiveRequirement:
    """Tests for POST /api/v2/proof/requirements/{req_id}/waive."""

    def _capture(self, test_client):
        return test_client.post(
            "/api/v2/proof/requirements",
            json={
                "title": "Waive test",
                "description": "Testing waiver endpoint",
                "where": "core/tasks.py",
                "severity": "low",
                "source": "qa",
            },
        ).json()["id"]

    def test_waive_returns_200(self, test_client):
        """Waiving a requirement returns 200."""
        req_id = self._capture(test_client)
        response = test_client.post(
            f"/api/v2/proof/requirements/{req_id}/waive",
            json={"reason": "Deferred to next sprint", "approved_by": "team-lead"},
        )
        assert response.status_code == 200

    def test_waive_changes_status(self, test_client):
        """Status changes to 'waived' after waiving."""
        req_id = self._capture(test_client)
        response = test_client.post(
            f"/api/v2/proof/requirements/{req_id}/waive",
            json={"reason": "Deferred"},
        )
        assert response.json()["status"] == "waived"

    def test_waive_with_expiry(self, test_client):
        """Waiver with expires date is accepted."""
        req_id = self._capture(test_client)
        response = test_client.post(
            f"/api/v2/proof/requirements/{req_id}/waive",
            json={"reason": "Short-term waiver", "expires": "2026-06-01"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["waiver"] is not None
        assert data["waiver"]["reason"] == "Short-term waiver"

    def test_waive_nonexistent_returns_404(self, test_client):
        """Waiving unknown requirement returns 404."""
        response = test_client.post(
            "/api/v2/proof/requirements/REQ-9999/waive",
            json={"reason": "Does not exist"},
        )
        assert response.status_code == 404

    def test_waive_missing_reason_returns_422(self, test_client):
        """Missing reason returns 422."""
        req_id = self._capture(test_client)
        response = test_client.post(
            f"/api/v2/proof/requirements/{req_id}/waive",
            json={},
        )
        assert response.status_code == 422


# ============================================================================
# GET /api/v2/proof/status — aggregated proof status
# ============================================================================


class TestProofStatus:
    """Tests for GET /api/v2/proof/status."""

    def test_status_empty(self, test_client):
        """Status returns zeros when no requirements."""
        response = test_client.get("/api/v2/proof/status")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert "open" in data
        assert "satisfied" in data
        assert "waived" in data

    def test_status_counts_requirements(self, test_client):
        """Status counts captured requirements correctly."""
        test_client.post(
            "/api/v2/proof/requirements",
            json={
                "title": "Status count test",
                "description": "A bug for status test",
                "where": "core/tasks.py",
                "severity": "medium",
                "source": "qa",
            },
        )
        response = test_client.get("/api/v2/proof/status")
        data = response.json()
        assert data["total"] == 1
        assert data["open"] == 1
        assert data["satisfied"] == 0
        assert data["waived"] == 0

    def test_status_includes_requirements_list(self, test_client):
        """Response includes full requirements list."""
        response = test_client.get("/api/v2/proof/status")
        data = response.json()
        assert "requirements" in data
        assert isinstance(data["requirements"], list)


# ============================================================================
# GET /api/v2/proof/requirements/{req_id}/evidence — list evidence
# ============================================================================


class TestListEvidence:
    """Tests for GET /api/v2/proof/requirements/{req_id}/evidence."""

    def _capture(self, test_client):
        return test_client.post(
            "/api/v2/proof/requirements",
            json={
                "title": "Evidence test",
                "description": "A bug for evidence test",
                "where": "core/tasks.py",
                "severity": "low",
                "source": "qa",
            },
        ).json()["id"]

    def test_evidence_empty_for_new_requirement(self, test_client):
        """New requirement has no evidence."""
        req_id = self._capture(test_client)
        response = test_client.get(f"/api/v2/proof/requirements/{req_id}/evidence")
        assert response.status_code == 200
        assert response.json() == []

    def test_evidence_nonexistent_returns_404(self, test_client):
        """Evidence for unknown requirement returns 404."""
        response = test_client.get("/api/v2/proof/requirements/REQ-9999/evidence")
        assert response.status_code == 404


# ============================================================================
# Error Response Format
# ============================================================================


class TestErrorResponses:
    """Verify all v2-style structured error responses."""

    def test_404_format(self, test_client):
        """404 errors include error, code, detail fields."""
        response = test_client.get("/api/v2/proof/requirements/REQ-9999")
        assert response.status_code == 404
        detail = response.json()["detail"]
        assert "error" in detail
        assert "code" in detail

    def test_400_format(self, test_client):
        """400 errors include error and code fields."""
        response = test_client.get("/api/v2/proof/requirements?status=invalid")
        assert response.status_code == 400
        detail = response.json()["detail"]
        assert "error" in detail
        assert "code" in detail


# ============================================================================
# GET /api/v2/proof/runs — list run history
# ============================================================================


class TestListRuns:
    """Tests for GET /api/v2/proof/runs."""

    def _capture_req(self, test_client):
        return test_client.post(
            "/api/v2/proof/requirements",
            json={
                "title": "Run history test req",
                "description": "A requirement for run history testing",
                "where": "core/tasks.py",
                "severity": "low",
                "source": "qa",
            },
        ).json()["id"]

    def test_list_runs_empty_initially(self, test_client):
        """No runs recorded before any proof run is triggered."""
        response = test_client.get("/api/v2/proof/runs")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_runs_after_run(self, test_client):
        """A completed run appears in the list."""
        self._capture_req(test_client)
        test_client.post("/api/v2/proof/run", json={"full": True})
        response = test_client.get("/api/v2/proof/runs")
        assert response.status_code == 200
        runs = response.json()
        assert len(runs) >= 1

    def test_list_runs_response_shape(self, test_client):
        """Each run summary has the expected fields."""
        self._capture_req(test_client)
        test_client.post("/api/v2/proof/run", json={"full": True})
        runs = test_client.get("/api/v2/proof/runs").json()
        assert len(runs) >= 1
        run = runs[0]
        for field in ["run_id", "started_at", "completed_at", "triggered_by",
                      "overall_passed", "duration_ms"]:
            assert field in run, f"Missing field: {field}"

    def test_list_runs_limit(self, test_client):
        """Limit parameter is respected."""
        self._capture_req(test_client)
        for _ in range(3):
            test_client.post("/api/v2/proof/run", json={"full": True})
        runs_limited = test_client.get("/api/v2/proof/runs?limit=2").json()
        assert len(runs_limited) <= 2

    def test_list_runs_ordered_newest_first(self, test_client):
        """Runs are returned newest-first."""
        self._capture_req(test_client)
        for _ in range(2):
            test_client.post("/api/v2/proof/run", json={"full": True})
        runs = test_client.get("/api/v2/proof/runs").json()
        if len(runs) >= 2:
            assert runs[0]["started_at"] >= runs[1]["started_at"]


# ============================================================================
# GET /api/v2/proof/runs/{run_id}/evidence — run evidence detail
# ============================================================================


class TestGetRunEvidence:
    """Tests for GET /api/v2/proof/runs/{run_id}/evidence."""

    def _capture_req(self, test_client):
        return test_client.post(
            "/api/v2/proof/requirements",
            json={
                "title": "Run evidence test req",
                "description": "A requirement for run evidence testing",
                "where": "core/tasks.py",
                "severity": "low",
                "source": "qa",
            },
        ).json()["id"]

    def test_get_run_evidence_shape(self, test_client):
        """Run evidence response has expected fields including evidence list."""
        self._capture_req(test_client)
        run_resp = test_client.post("/api/v2/proof/run", json={"full": True}).json()
        run_id = run_resp["run_id"]

        response = test_client.get(f"/api/v2/proof/runs/{run_id}/evidence")
        assert response.status_code == 200
        data = response.json()
        for field in ["run_id", "started_at", "completed_at", "triggered_by",
                      "overall_passed", "duration_ms", "evidence"]:
            assert field in data, f"Missing field: {field}"
        assert isinstance(data["evidence"], list)

    def test_get_run_evidence_unknown_returns_404(self, test_client):
        """Unknown run_id returns 404."""
        response = test_client.get("/api/v2/proof/runs/nonexistent-run/evidence")
        assert response.status_code == 404

    def test_get_run_evidence_each_item_has_artifact_text(self, test_client):
        """Each evidence item has an artifact_text field."""
        self._capture_req(test_client)
        run_resp = test_client.post("/api/v2/proof/run", json={"full": True}).json()
        run_id = run_resp["run_id"]

        data = test_client.get(f"/api/v2/proof/runs/{run_id}/evidence").json()
        for ev in data["evidence"]:
            assert "artifact_text" in ev, "Evidence item missing artifact_text"
