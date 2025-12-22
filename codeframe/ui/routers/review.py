"""Review router for CodeFRAME FastAPI server.

Handles code review endpoints including triggering reviews, retrieving review
results, and managing review statistics.

Sprint 9 & Sprint 10 endpoints:
- POST /api/agents/{agent_id}/review - Trigger code review for a task
- GET /api/tasks/{task_id}/review-status - Get review status for a task
- GET /api/projects/{project_id}/review-stats - Get aggregated review statistics
- POST /api/agents/review/analyze - Trigger code review analysis (background)
- GET /api/tasks/{task_id}/reviews - Get code review findings for a task
- GET /api/projects/{project_id}/code-reviews - Get project-level code reviews
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Request, Depends
from typing import Optional
from datetime import datetime, UTC
import logging
import uuid

from codeframe.ui.models import ReviewRequest
from codeframe.ui.dependencies import get_db
from codeframe.ui.auth import get_current_user, User
from codeframe.ui.shared import manager, review_cache
from codeframe.persistence.database import Database
from codeframe.agents.review_worker_agent import ReviewWorkerAgent
from codeframe.agents.review_agent import ReviewAgent
from codeframe.core.models import Task

# Module logger
logger = logging.getLogger(__name__)

# Create router without prefix since review endpoints have mixed prefixes
# (/api/agents, /api/tasks, /api/projects)
router = APIRouter(tags=["review"])


@router.post("/api/agents/{agent_id}/review")
async def trigger_review(
    agent_id: str,
    request: ReviewRequest,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger code review for a task (T056).

    Sprint 9 - User Story 1: Review Agent API

    Executes code review using ReviewWorkerAgent and returns review report
    with findings, scores, and recommendations.

    Args:
        agent_id: Review agent ID to use
        request: ReviewRequest with task_id, project_id, files_modified
        db: Database connection (injected)

    Returns:
        200 OK: ReviewReport with status, overall_score, findings
        500 Internal Server Error: Review execution failed

    Example:
        POST /api/agents/review-001/review
        Body: {
            "task_id": 42,
            "project_id": 123,
            "files_modified": ["/path/to/file.py"]
        }

        Response: {
            "status": "approved",
            "overall_score": 85.5,
            "findings": [
                {
                    "category": "complexity",
                    "severity": "medium",
                    "message": "Function has complexity of 12",
                    "file_path": "/path/to/file.py",
                    "line_number": 42,
                    "suggestion": "Consider breaking into smaller functions"
                }
            ],
            "reviewer_agent_id": "review-001",
            "task_id": 42
        }
    """
    try:
        # Verify project exists and user has access
        project = db.get_project(request.project_id)
        if not project:
            raise HTTPException(
                status_code=404, detail=f"Project {request.project_id} not found"
            )

        # Authorization check
        if not db.user_has_project_access(current_user.id, request.project_id):
            raise HTTPException(status_code=403, detail="Access denied")

        # Emit review started event (T059)
        await manager.broadcast(
            {
                "type": "review_started",
                "agent_id": agent_id,
                "project_id": request.project_id,
                "task_id": request.task_id,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

        # Create review agent
        review_agent = ReviewWorkerAgent(agent_id=agent_id, db=db)

        # Get task data from database
        task_data = db.get_task(request.task_id)
        if not task_data:
            raise HTTPException(status_code=404, detail=f"Task {request.task_id} not found")

        # Build task dict for execute_task
        task = {
            "id": request.task_id,
            "task_number": task_data.task_number or "unknown",
            "title": task_data.title or "",
            "description": task_data.description or "",
            "files_modified": request.files_modified,
            "project_id": task_data.project_id,
        }

        # Execute review
        report = await review_agent.execute_task(task)

        if not report:
            raise HTTPException(status_code=500, detail="Review failed to produce report")

        # Cache the review report for later retrieval (T057, T058)
        report_dict = report.model_dump()
        report_dict["project_id"] = request.project_id  # Add project_id for filtering
        review_cache[request.task_id] = report_dict

        # Emit WebSocket event based on review status (T059)
        event_type_map = {
            "approved": "review_approved",
            "changes_requested": "review_changes_requested",
            "rejected": "review_rejected",
        }
        event_type = event_type_map.get(report.status, "review_completed")

        await manager.broadcast(
            {
                "type": event_type,
                "agent_id": agent_id,
                "project_id": request.project_id,
                "task_id": request.task_id,
                "status": report.status,
                "overall_score": report.overall_score,
                "findings_count": len(report.findings),
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

        # Return report as dict
        return report_dict

    except HTTPException:
        raise
    except Exception as e:
        # Emit failure event
        await manager.broadcast(
            {
                "type": "review_failed",
                "agent_id": agent_id,
                "project_id": request.project_id,
                "task_id": request.task_id,
                "error": str(e),
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        raise HTTPException(status_code=500, detail=f"Review execution failed: {str(e)}")


@router.get("/api/tasks/{task_id}/review-status")
async def get_review_status(
    task_id: int, db: Database = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """Get review status for a task (T057).

    Returns the cached review report if available, otherwise indicates no review exists.

    Args:
        task_id: Task ID to get review status for

    Returns:
        200 OK: Review status object

    Example:
        GET /api/tasks/123/review-status
        Response: {
            "has_review": true,
            "status": "approved",
            "overall_score": 85.5,
            "findings_count": 3
        }
    """
    try:
        # Get task to obtain project_id for authorization
        task = db.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        project_id = task.project_id

        # Authorization check
        if not db.user_has_project_access(current_user.id, project_id):
            raise HTTPException(status_code=403, detail="Access denied")

        # Check if review exists in cache
        if task_id in review_cache:
            report = review_cache[task_id]
            return {
                "has_review": True,
                "status": report["status"],
                "overall_score": report["overall_score"],
                "findings_count": len(report.get("findings", [])),
            }
        else:
            # No review exists yet
            return {
                "has_review": False,
                "status": None,
                "overall_score": None,
                "findings_count": 0,
            }
    except HTTPException:
        # Re-raise HTTPException (including 403 Forbidden) without masking
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get review status: {str(e)}")


@router.get("/api/projects/{project_id}/review-stats")
async def get_review_stats(
    project_id: int,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get aggregated review statistics for a project (T058).

    Returns counts and averages for all reviews in the project.

    Args:
        project_id: Project ID to get review stats for

    Returns:
        200 OK: Review statistics object

    Example:
        GET /api/projects/123/review-stats
        Response: {
            "total_reviews": 5,
            "approved_count": 3,
            "changes_requested_count": 1,
            "rejected_count": 1,
            "average_score": 75.5
        }
    """
    try:
        # Verify project exists
        project = db.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        # Authorization check
        if not db.user_has_project_access(current_user.id, project_id):
            raise HTTPException(status_code=403, detail="Access denied")

        # Filter reviews for this project
        project_reviews = [
            report for report in review_cache.values() if report.get("project_id") == project_id
        ]

        # Calculate stats
        total_reviews = len(project_reviews)

        if total_reviews == 0:
            return {
                "total_reviews": 0,
                "approved_count": 0,
                "changes_requested_count": 0,
                "rejected_count": 0,
                "average_score": 0.0,
            }

        # Count by status
        approved_count = sum(1 for r in project_reviews if r.get("status") == "approved")
        changes_requested_count = sum(
            1 for r in project_reviews if r.get("status") == "changes_requested"
        )
        rejected_count = sum(1 for r in project_reviews if r.get("status") == "rejected")

        # Calculate average score
        total_score = sum(r.get("overall_score", 0) for r in project_reviews)
        average_score = round(total_score / total_reviews, 1) if total_reviews > 0 else 0.0

        return {
            "total_reviews": total_reviews,
            "approved_count": approved_count,
            "changes_requested_count": changes_requested_count,
            "rejected_count": rejected_count,
            "average_score": average_score,
        }

    except HTTPException:
        # Re-raise HTTPException (including 403 Forbidden) without masking
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get review stats: {str(e)}")


# Sprint 10 Phase 2: Review Agent API endpoints (T034, T035)


@router.post("/api/agents/review/analyze", status_code=202)
async def analyze_code_review(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger code review analysis for a task (T034).

    Sprint 10 - Phase 2: Review Agent API

    Accepts a task_id and optional project_id, creates a ReviewAgent instance,
    and executes the review in a background task. Returns immediately with job status.

    Args:
        request: FastAPI request containing:
            - task_id: int (required) - Task ID to review
            - project_id: int (optional) - Project ID for scoping
        background_tasks: FastAPI background tasks
        db: Database connection (injected)

    Returns:
        202 Accepted: Review job started
        {
            "job_id": str,
            "status": "started",
            "message": "Code review analysis started for task {task_id}"
        }

        400 Bad Request: Invalid request (missing task_id)
        404 Not Found: Task not found

    Example:
        POST /api/agents/review/analyze
        Body: {
            "task_id": 42,
            "project_id": 123
        }
    """
    try:
        # Parse request body
        data = await request.json()
        task_id = data.get("task_id")
        project_id = data.get("project_id")

        # Validate task_id
        if not task_id:
            raise HTTPException(status_code=400, detail="task_id is required")

        # Check if task exists
        task_data = db.get_task(task_id)
        if not task_data:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        # Use project_id from request or task data
        if not project_id:
            project_id = task_data.project_id

        # Verify project exists
        project = db.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        # Authorization check
        if not db.user_has_project_access(current_user.id, project_id):
            raise HTTPException(status_code=403, detail="Access denied")

        # Generate job ID
        job_id = str(uuid.uuid4())

        # Capture app reference for background task (db is request-scoped)
        app = request.app

        # Create background task to run review
        async def run_review():
            """Background task to execute code review."""
            try:
                # Get database connection from app state (not request-scoped)
                task_db = app.state.db

                # Create ReviewAgent instance
                review_agent = ReviewAgent(
                    agent_id=f"review-{job_id[:8]}",
                    db=task_db,
                    project_id=project_id,
                    ws_manager=manager,
                )

                # Build Task object from task_data
                task = Task(
                    id=task_id,
                    title=task_data.title or "",
                    description=task_data.description or "",
                    project_id=project_id,
                    status=task_data.status,
                    priority=task_data.priority,
                )

                # Execute review (this saves findings to database)
                result = await review_agent.execute_task(task)

                logger.info(
                    f"Review job {job_id} completed: {result.status}, "
                    f"{len(result.findings)} findings"
                )

            except Exception as e:
                logger.error(f"Review job {job_id} failed: {e}", exc_info=True)

        # Add background task
        background_tasks.add_task(run_review)

        # Return 202 Accepted immediately
        return {
            "job_id": job_id,
            "status": "started",
            "message": f"Code review analysis started for task {task_id}",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start code review: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start review: {str(e)}")


def _extract_enum_value_for_counting(obj, attr_name: str):
    """Extract enum value or string for counting logic.

    Returns None if attribute is missing or None (to skip counting),
    otherwise returns the string value or enum.value.

    Args:
        obj: Object to extract attribute from
        attr_name: Name of the attribute (e.g., 'severity', 'category')

    Returns:
        str | None: The extracted value or None
    """
    if not hasattr(obj, attr_name):
        return None

    attr = getattr(obj, attr_name)
    if attr is None:
        return None

    # Check if it's an enum with .value
    if hasattr(attr, "value"):
        return attr.value

    # Otherwise convert to string
    return str(attr)


def _extract_enum_value(obj, attr_name: str, default: str):
    """Extract enum value or string with default fallback.

    Returns default when attribute is missing or None,
    otherwise returns the string value or enum.value.

    Args:
        obj: Object to extract attribute from
        attr_name: Name of the attribute (e.g., 'severity', 'category')
        default: Default value to return if attribute is missing/None

    Returns:
        str: The extracted value or default
    """
    if not hasattr(obj, attr_name):
        return default

    attr = getattr(obj, attr_name)
    if attr is None:
        return default

    # Check if it's an enum with .value
    if hasattr(attr, "value"):
        return attr.value

    # Otherwise convert to string
    return str(attr)


@router.get("/api/tasks/{task_id}/reviews")
async def get_task_reviews(
    task_id: int,
    severity: Optional[str] = None,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get code review findings for a task (T035).

    Sprint 10 - Phase 2: Review Agent API

    Returns all code review findings for a specific task, optionally filtered by severity.
    Includes summary statistics (total findings, counts by severity, blocking status).

    Args:
        task_id: Task ID to get reviews for
        severity: Optional severity filter (critical, high, medium, low, info)
        db: Database connection (injected)

    Returns:
        200 OK: Review findings with summary statistics (matches ReviewResult interface)
        {
            "task_id": int,
            "findings": [
                {
                    "id": int,
                    "task_id": int,
                    "agent_id": str,
                    "project_id": int,
                    "file_path": str,
                    "line_number": int | null,
                    "severity": str,
                    "category": str,
                    "message": str,
                    "recommendation": str | null,
                    "code_snippet": str | null,
                    "created_at": str
                },
                ...
            ],
            "total_count": int,
            "severity_counts": {
                "critical": int,
                "high": int,
                "medium": int,
                "low": int,
                "info": int
            },
            "category_counts": {
                "security": int,
                "performance": int,
                "quality": int,
                "maintainability": int,
                "style": int
            },
            "has_blocking_findings": bool
        }

        400 Bad Request: Invalid severity value
        404 Not Found: Task not found

    Example:
        GET /api/tasks/42/reviews
        GET /api/tasks/42/reviews?severity=critical
    """
    # Validate severity if provided
    valid_severities = ["critical", "high", "medium", "low", "info"]
    if severity and severity not in valid_severities:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid severity. Must be one of: {', '.join(valid_severities)}",
        )

    # Check if task exists
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    # Authorization check - get project_id from task
    project_id = task.project_id
    if not db.user_has_project_access(current_user.id, project_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Get code reviews from database
    reviews = db.get_code_reviews(task_id=task_id, severity=severity)

    # Build summary statistics
    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}

    category_counts = {
        "security": 0,
        "performance": 0,
        "quality": 0,
        "maintainability": 0,
        "style": 0,
    }

    for review in reviews:
        # Extract severity and category using helper (returns None if missing/invalid)
        severity_val = _extract_enum_value_for_counting(review, "severity")
        if severity_val and severity_val in severity_counts:
            severity_counts[severity_val] += 1

        category_val = _extract_enum_value_for_counting(review, "category")
        if category_val and category_val in category_counts:
            category_counts[category_val] += 1

    # Blocking issues are critical or high severity
    has_blocking_findings = (severity_counts["critical"] + severity_counts["high"]) > 0

    # Convert CodeReview objects to dictionaries
    findings_data = []
    for review in reviews:
        # Extract severity and category using helper (returns default if missing/invalid)
        severity_val = _extract_enum_value(review, "severity", "unknown")
        category_val = _extract_enum_value(review, "category", "unknown")

        findings_data.append(
            {
                "id": review.id,
                "task_id": review.task_id,
                "agent_id": review.agent_id,
                "project_id": review.project_id,
                "file_path": review.file_path,
                "line_number": review.line_number,
                "severity": severity_val,
                "category": category_val,
                "message": review.message,
                "recommendation": review.recommendation,
                "code_snippet": review.code_snippet,
                "created_at": review.created_at,
            }
        )

    # Build response matching ReviewResult interface
    return {
        "task_id": task_id,
        "findings": findings_data,
        "total_count": len(reviews),
        "severity_counts": severity_counts,
        "category_counts": category_counts,
        "has_blocking_findings": has_blocking_findings,
    }


@router.get("/api/projects/{project_id}/code-reviews")
async def get_project_code_reviews(
    project_id: int,
    severity: Optional[str] = None,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get aggregated code review findings for all tasks in a project.

    Returns all code review findings across all tasks in the project,
    optionally filtered by severity. Includes summary statistics aggregated
    at the project level.

    Args:
        project_id: Project ID to fetch reviews for
        severity: Optional severity filter (critical, high, medium, low, info)
        db: Database connection (injected)

    Returns:
        200 OK: Review findings with project-level summary statistics
        {
            "findings": [
                {
                    "id": int,
                    "task_id": int,
                    "agent_id": str,
                    "project_id": int,
                    "file_path": str,
                    "line_number": int | null,
                    "severity": str,
                    "category": str,
                    "message": str,
                    "recommendation": str | null,
                    "code_snippet": str | null,
                    "created_at": str
                },
                ...
            ],
            "summary": {
                "total_findings": int,
                "by_severity": {
                    "critical": int,
                    "high": int,
                    "medium": int,
                    "low": int,
                    "info": int
                },
                "by_category": {
                    "security": int,
                    "performance": int,
                    "quality": int,
                    "maintainability": int,
                    "style": int
                },
                "has_blocking_issues": bool
            },
            "task_id": null
        }

        400 Bad Request: Invalid severity value
        404 Not Found: Project not found

    Example:
        GET /api/projects/2/code-reviews
        GET /api/projects/2/code-reviews?severity=critical
    """
    # Validate severity if provided
    valid_severities = ["critical", "high", "medium", "low", "info"]
    if severity and severity not in valid_severities:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid severity. Must be one of: {', '.join(valid_severities)}",
        )

    # Check if project exists
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # Authorization check
    if not db.user_has_project_access(current_user.id, project_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Get code reviews from database
    reviews = db.get_code_reviews_by_project(project_id=project_id, severity=severity)

    # Build summary statistics
    by_severity = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}

    by_category = {"security": 0, "performance": 0, "quality": 0, "maintainability": 0, "style": 0}

    for review in reviews:
        # Extract severity and category using helper (returns None if missing/invalid)
        severity_val = _extract_enum_value_for_counting(review, "severity")
        if severity_val and severity_val in by_severity:
            by_severity[severity_val] += 1

        category_val = _extract_enum_value_for_counting(review, "category")
        if category_val and category_val in by_category:
            by_category[category_val] += 1

    # Blocking issues are critical or high severity
    has_blocking_issues = (by_severity["critical"] + by_severity["high"]) > 0

    # Convert CodeReview objects to dictionaries
    findings_data = []
    for review in reviews:
        # Extract severity and category using helper (returns default if missing/invalid)
        severity_val = _extract_enum_value(review, "severity", "unknown")
        category_val = _extract_enum_value(review, "category", "unknown")

        findings_data.append(
            {
                "id": review.id,
                "task_id": review.task_id,
                "agent_id": review.agent_id,
                "project_id": review.project_id,
                "file_path": review.file_path,
                "line_number": review.line_number,
                "severity": severity_val,
                "category": category_val,
                "message": review.message,
                "recommendation": review.recommendation,
                "code_snippet": review.code_snippet,
                "created_at": review.created_at,
            }
        )

    # Build response (matches get_task_reviews flat structure)
    return {
        "findings": findings_data,
        "total_count": len(reviews),
        "severity_counts": by_severity,
        "category_counts": by_category,
        "has_blocking_findings": has_blocking_issues,
        "task_id": None,  # Project-level aggregate
    }
