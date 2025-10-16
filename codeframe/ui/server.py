"""FastAPI Status Server for CodeFRAME."""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from typing import List, Dict, Any
import asyncio
import json

from codeframe.core.project import Project
from codeframe.core.models import TaskStatus, AgentMaturity

app = FastAPI(
    title="CodeFRAME Status Server",
    description="Real-time monitoring and control for CodeFRAME projects",
    version="0.1.0"
)

# CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],  # React/Vite dev servers
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ConnectionManager:
    """Manage WebSocket connections for real-time updates."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients."""
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                # Client disconnected
                pass


manager = ConnectionManager()


# API Routes

@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "online", "service": "CodeFRAME Status Server"}


@app.get("/api/projects")
async def list_projects():
    """List all CodeFRAME projects."""
    # TODO: Implement project discovery
    return {
        "projects": [
            {
                "id": 1,
                "name": "example-project",
                "status": "active",
                "progress": 65
            }
        ]
    }


@app.get("/api/projects/{project_id}/status")
async def get_project_status(project_id: int):
    """Get comprehensive project status."""
    # TODO: Load project and gather status
    return {
        "project_id": project_id,
        "project_name": "example-project",
        "status": "active",
        "phase": "execution",
        "workflow_step": 7,
        "progress": {
            "completed_tasks": 26,
            "total_tasks": 40,
            "percentage": 65
        },
        "time_tracking": {
            "started_at": "2025-01-15T09:00:00Z",
            "elapsed_hours": 3.5,
            "estimated_remaining_hours": 2.25
        },
        "cost_tracking": {
            "input_tokens": 1200000,
            "output_tokens": 450000,
            "estimated_cost": 8.50
        }
    }


@app.get("/api/projects/{project_id}/agents")
async def get_agent_status(project_id: int):
    """Get status of all agents."""
    # TODO: Query database for agent status
    return {
        "agents": [
            {
                "id": "lead",
                "type": "lead",
                "provider": "claude",
                "maturity": "supporting",
                "status": "working",
                "current_task": None,
                "last_action": "Coordinating task assignments",
                "context_tokens": 45000
            },
            {
                "id": "backend-1",
                "type": "backend",
                "provider": "claude",
                "maturity": "coaching",
                "status": "working",
                "current_task": {
                    "id": 27,
                    "title": "JWT refresh token flow"
                },
                "progress": 45,
                "tests_passing": 3,
                "tests_total": 5,
                "context_tokens": 85000
            },
            {
                "id": "frontend-1",
                "type": "frontend",
                "provider": "gpt4",
                "maturity": "directive",
                "status": "blocked",
                "current_task": {
                    "id": 28,
                    "title": "Login UI components"
                },
                "blocker": "Waiting on Task #27 (backend API)"
            },
            {
                "id": "test-1",
                "type": "test",
                "provider": "claude",
                "maturity": "supporting",
                "status": "working",
                "current_task": {
                    "id": 29,
                    "title": "E2E auth flow tests"
                },
                "progress": 70
            }
        ]
    }


@app.get("/api/projects/{project_id}/tasks")
async def get_tasks(
    project_id: int,
    status: str | None = None,
    limit: int = 50
):
    """Get project tasks."""
    # TODO: Query database with filters
    return {
        "tasks": [
            {
                "id": 27,
                "title": "JWT refresh token flow",
                "description": "Implement token refresh endpoint",
                "status": "in_progress",
                "assigned_to": "backend-1",
                "priority": 0,
                "workflow_step": 7,
                "progress": 45
            }
        ],
        "total": 40
    }


@app.get("/api/projects/{project_id}/blockers")
async def get_blockers(project_id: int):
    """Get pending blockers requiring user input."""
    # TODO: Query database for unresolved blockers
    return {
        "blockers": [
            {
                "id": 1,
                "task_id": 30,
                "severity": "sync",
                "question": "Should password reset tokens expire after 1hr or 24hrs?",
                "reason": "Security vs UX trade-off",
                "created_at": "2025-01-15T14:00:00Z",
                "blocking_agents": ["backend-1", "test-1"]
            },
            {
                "id": 2,
                "task_id": 25,
                "severity": "async",
                "question": "Use Material UI or Ant Design for form components?",
                "reason": "Design system choice",
                "created_at": "2025-01-15T12:00:00Z",
                "blocking_agents": []
            }
        ]
    }


@app.post("/api/projects/{project_id}/blockers/{blocker_id}/resolve")
async def resolve_blocker(project_id: int, blocker_id: int, resolution: Dict[str, str]):
    """Resolve a blocker with user's answer."""
    # TODO: Update database and notify Lead Agent
    answer = resolution.get("answer")

    # Broadcast update to WebSocket clients
    await manager.broadcast({
        "type": "blocker_resolved",
        "blocker_id": blocker_id,
        "answer": answer
    })

    return {
        "success": True,
        "blocker_id": blocker_id,
        "message": "Blocker resolved, agents resuming work"
    }


@app.get("/api/projects/{project_id}/activity")
async def get_activity(project_id: int, limit: int = 50):
    """Get recent activity log."""
    # TODO: Query changelog table
    return {
        "activity": [
            {
                "timestamp": "2025-01-15T14:32:00Z",
                "type": "task_completed",
                "agent": "backend-1",
                "message": "Completed Task #26 (login endpoint)"
            },
            {
                "timestamp": "2025-01-15T14:28:00Z",
                "type": "tests_passed",
                "agent": "test-1",
                "message": "All tests passed for auth module"
            },
            {
                "timestamp": "2025-01-15T14:15:00Z",
                "type": "blocker_created",
                "agent": "backend-1",
                "message": "Escalated blocker on Task #30"
            }
        ]
    }


@app.post("/api/projects/{project_id}/chat")
async def chat_with_lead(project_id: int, message: Dict[str, str]):
    """Chat with Lead Agent."""
    user_message = message.get("message")

    # TODO: Send to Lead Agent and get response
    response = f"I received your message: {user_message}"

    return {
        "response": response,
        "timestamp": "2025-01-15T14:35:00Z"
    }


@app.post("/api/projects/{project_id}/pause")
async def pause_project(project_id: int):
    """Pause project execution."""
    # TODO: Trigger flash save and pause agents
    return {"success": True, "message": "Project paused"}


@app.post("/api/projects/{project_id}/resume")
async def resume_project(project_id: int):
    """Resume project execution."""
    # TODO: Restore from checkpoint and resume agents
    return {"success": True, "message": "Project resuming"}


# WebSocket for real-time updates

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket connection for real-time updates."""
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive and handle incoming messages
            data = await websocket.receive_text()
            message = json.loads(data)

            # Handle different message types
            if message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
            elif message.get("type") == "subscribe":
                # Subscribe to specific project updates
                project_id = message.get("project_id")
                # TODO: Track subscriptions
                await websocket.send_json({
                    "type": "subscribed",
                    "project_id": project_id
                })

    except WebSocketDisconnect:
        manager.disconnect(websocket)


# Background task to broadcast updates
async def broadcast_updates():
    """Periodically broadcast project updates to connected clients."""
    while True:
        await asyncio.sleep(5)  # Update every 5 seconds

        # TODO: Gather latest project state
        update = {
            "type": "status_update",
            "timestamp": "2025-01-15T14:35:00Z",
            "data": {
                "progress": 65,
                "active_agents": 3,
                "completed_tasks": 26
            }
        }

        await manager.broadcast(update)


@app.on_event("startup")
async def startup_event():
    """Start background tasks."""
    # TODO: Start background update broadcaster
    # asyncio.create_task(broadcast_updates())
    pass


def run_server(host: str = "0.0.0.0", port: int = 8080):
    """Run the Status Server."""
    import uvicorn
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()
