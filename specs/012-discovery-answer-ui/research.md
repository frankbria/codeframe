# Research: Discovery Answer UI Integration

**Feature**: 012-discovery-answer-ui
**Date**: 2025-11-19
**Phase**: 0 (Research & Design)

---

## Research Questions

This document answers the "NEEDS CLARIFICATION" items identified in plan.md:

1. Where are discovery answers stored in the database?
2. Is WebSocket broadcast required for answer submission events?
3. Does `LeadAgent.process_discovery_answer()` method exist or need creation?

---

## Question 1: Discovery Answer Storage

### Decision
Use the existing `memory` table with category `"discovery_answers"`.

### Evidence

**Database Schema** (`codeframe/persistence/database.py:193-206`):
```python
CREATE TABLE IF NOT EXISTS memory (
    id INTEGER PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id),
    category TEXT CHECK(category IN (
        'pattern', 'decision', 'gotcha', 'preference',
        'conversation', 'discovery_state', 'discovery_answers', 'prd'
    )),
    key TEXT,
    value TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

**Lead Agent Implementation** (`codeframe/agents/lead_agent.py:211-250, 325-330`):
```python
# Loading discovery answers
answer_memories = [m for m in all_memories if m["category"] == "discovery_answers"]

# Saving discovery answers
self.db.create_memory(
    project_id=self.project_id,
    category="discovery_answers",
    key=self._current_question_id,
    value=answer,
)
```

### Rationale

**Why this approach**:
- ✅ Schema already exists with CHECK constraint validation
- ✅ Leverages existing `create_memory()` and `get_project_memories()` methods
- ✅ Consistent with discovery state storage pattern
- ✅ Supports project-scoped storage for multi-project collaboration
- ✅ No migration required

**Storage Format**:
- **category**: `"discovery_answers"`
- **key**: Question ID (e.g., `"q_project_problem"`, `"q_target_users"`)
- **value**: User's answer text (JSON string if structured data needed)
- **project_id**: Scopes answers to specific project

**Alternatives Considered**:

1. **Separate `discovery_answers` table**
   - **Rejected**: Adds complexity without benefit
   - **Why**: memory table provides flexible key-value storage already

2. **Store in `projects` table as JSON column**
   - **Rejected**: Violates normalization, difficult to query
   - **Why**: memory table provides better queryability and history

---

## Question 2: WebSocket Broadcast Requirements

### Decision
WebSocket broadcasts ARE required. Add 4 new broadcast functions following existing patterns.

### Evidence

**Existing Broadcast Infrastructure** (`codeframe/ui/websocket_broadcasts.py:1-627`):
- Comprehensive broadcast functions for: tasks, agents, tests, commits, blockers, activity
- Standard pattern: async functions with manager, logging, error handling
- Test coverage: `tests/ui/test_websocket_broadcasts.py`

**Example Pattern** (from `broadcast_blocker_created:490-540`):
```python
async def broadcast_blocker_created(
    manager,
    project_id: int,
    blocker_id: int,
    question: str,
    priority: str,
) -> None:
    """Broadcast blocker creation to connected clients."""
    message = {
        "type": "blocker_created",
        "project_id": project_id,
        "blocker": {
            "id": blocker_id,
            "question": question,
            "priority": priority,
        },
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    try:
        await manager.broadcast(message)
        logger.debug(f"Broadcast blocker_created: {blocker_id}")
    except Exception as e:
        logger.error(f"Failed to broadcast blocker creation: {e}")
```

### Required Broadcast Events

**1. `discovery_answer_submitted`**
```python
async def broadcast_discovery_answer_submitted(
    manager,
    project_id: int,
    question_id: str,
    answer_preview: str,  # First 100 chars
    current_index: int,
    total_questions: int,
) -> None:
    """Broadcast when user submits discovery answer."""
    message = {
        "type": "discovery_answer_submitted",
        "project_id": project_id,
        "question_id": question_id,
        "answer_preview": answer_preview,
        "progress": {
            "current": current_index,
            "total": total_questions,
            "percentage": round((current_index / total_questions) * 100, 1),
        },
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    await manager.broadcast(message)
```

**2. `discovery_question_presented`**
```python
async def broadcast_discovery_question_presented(
    manager,
    project_id: int,
    question_id: str,
    question_text: str,
    current_index: int,
    total_questions: int,
) -> None:
    """Broadcast when next discovery question is presented."""
    message = {
        "type": "discovery_question_presented",
        "project_id": project_id,
        "question_id": question_id,
        "question_text": question_text,
        "current_index": current_index,
        "total_questions": total_questions,
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    await manager.broadcast(message)
```

**3. `discovery_progress_updated`**
```python
async def broadcast_discovery_progress_updated(
    manager,
    project_id: int,
    current_index: int,
    total_questions: int,
    percentage: float,
) -> None:
    """Broadcast discovery progress updates."""
    message = {
        "type": "discovery_progress_updated",
        "project_id": project_id,
        "progress": {
            "current": current_index,
            "total": total_questions,
            "percentage": percentage,
        },
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    await manager.broadcast(message)
```

**4. `discovery_completed`**
```python
async def broadcast_discovery_completed(
    manager,
    project_id: int,
    total_answers: int,
    next_phase: str = "prd_generation",
) -> None:
    """Broadcast when discovery phase is completed."""
    message = {
        "type": "discovery_completed",
        "project_id": project_id,
        "total_answers": total_answers,
        "next_phase": next_phase,
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    await manager.broadcast(message)
```

### Rationale

**Why broadcasts are required**:
- ✅ Dashboard needs real-time updates for discovery progress
- ✅ Multiple users may be monitoring project (team collaboration)
- ✅ Answer submissions should trigger immediate UI feedback
- ✅ Completion triggers phase transition to planning in UI
- ✅ Consistent with existing real-time update architecture

**Frontend Integration**:
- WebSocket subscription in DiscoveryProgress component
- Update progress bar on `discovery_progress_updated`
- Display next question on `discovery_question_presented`
- Transition UI on `discovery_completed`
- Show confirmation on `discovery_answer_submitted`

**Testing**:
- Add 4 unit tests to `tests/ui/test_websocket_broadcasts.py`
- Follow existing test patterns (message format validation, timestamp checks)

---

## Question 3: Lead Agent Discovery Method

### Decision
Use existing `process_discovery_answer()` method. **NO new method creation needed.**

### Evidence

**Method Exists** (`codeframe/agents/lead_agent.py:303-352`):
```python
def process_discovery_answer(self, answer: str) -> str:
    """Process user answer during discovery phase.

    Saves the answer, advances to next question, and checks for completion.
    """
    if self._discovery_state != "discovering":
        logger.warning(f"process_discovery_answer called in state: {self._discovery_state}")
        return "Discovery is not active. Call start_discovery() first."

    # Save current answer
    if self._current_question_id:
        self._discovery_answers[self._current_question_id] = answer
        self.answer_capture.capture_answer(self._current_question_id, answer)

        # Persist to database
        self.db.create_memory(
            project_id=self.project_id,
            category="discovery_answers",
            key=self._current_question_id,
            value=answer,
        )

    # Advance to next question
    self._current_question_index += 1

    # Check if complete
    if self._current_question_index >= len(self._questions):
        self._discovery_state = "complete"
        self._save_discovery_state()
        return "Discovery complete! Ready to generate PRD."

    # Return next question
    next_question_data = self._questions[self._current_question_index]
    self._current_question_id = next_question_data["id"]
    self._save_discovery_state()

    return next_question_data["text"]
```

**Related Methods**:
- `start_discovery()` (lines 276-301) - Initializes discovery state
- `get_discovery_status()` (lines 354-408) - Returns comprehensive discovery status
- `_load_discovery_state()` (lines 211-250) - Loads from database on init
- `_save_discovery_state()` (lines 251-274) - Persists state to database
- `generate_prd()` (lines 423-482) - Creates PRD after completion

### Workflow

```
1. Project Created → Lead Agent Initialized
   ↓
2. Call lead_agent.start_discovery()
   ↓ (transitions to "discovering" state)
   ↓
3. User submits answer → API calls lead_agent.process_discovery_answer(answer)
   ↓ (saves to memory table, advances question index)
   ↓
4. API endpoint returns:
   - next_question_text
   - current_index
   - total_questions
   - is_complete (boolean)
   ↓
5. Repeat step 3 until is_complete = true
   ↓
6. Call lead_agent.generate_prd()
   ↓ (creates PRD from all answers)
   ↓
7. Project transitions to "planning" phase
```

### API Endpoint Integration

**Implementation** (`codeframe/ui/app.py`):
```python
from pydantic import BaseModel, Field

class DiscoveryAnswer(BaseModel):
    answer: str = Field(..., min_length=1, max_length=5000)

@app.post("/api/projects/{project_id}/discovery/answer")
async def submit_discovery_answer(
    project_id: int,
    answer: DiscoveryAnswer,
):
    """Submit answer to current discovery question."""
    # Validate project exists
    project = await db.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    # Validate discovery phase
    if project.phase != "discovery":
        raise HTTPException(400, "Project is not in discovery phase")

    # Get Lead Agent (from project manager or cache)
    lead_agent = await get_lead_agent(project_id)

    # Process answer using existing method
    result_message = lead_agent.process_discovery_answer(answer.answer)

    # Get updated discovery status
    status = lead_agent.get_discovery_status()

    # Broadcast events
    await broadcast_discovery_answer_submitted(
        manager=websocket_manager,
        project_id=project_id,
        question_id=status["current_question_id"],
        answer_preview=answer.answer[:100],
        current_index=status["current_question_index"],
        total_questions=status["total_questions"],
    )

    if status["is_complete"]:
        await broadcast_discovery_completed(
            manager=websocket_manager,
            project_id=project_id,
            total_answers=status["answered_count"],
        )
    else:
        await broadcast_discovery_question_presented(
            manager=websocket_manager,
            project_id=project_id,
            question_id=status["current_question_id"],
            question_text=status["current_question"],
            current_index=status["current_question_index"],
            total_questions=status["total_questions"],
        )

    # Return updated state to frontend
    return {
        "success": True,
        "next_question": status.get("current_question"),
        "is_complete": status["is_complete"],
        "current_index": status["current_question_index"],
        "total_questions": status["total_questions"],
        "progress_percentage": status["progress_percentage"],
    }
```

### Rationale

**Why use existing method**:
- ✅ Method already implements complete workflow
- ✅ Database persistence already implemented
- ✅ State transitions handled (discovering → complete)
- ✅ Integrates with `AnswerCapture` for structured data extraction
- ✅ Follows existing patterns (error handling, logging)
- ✅ Returns appropriate next question or completion message
- ✅ Tested in `tests/agents/test_lead_agent.py` and `tests/planning/test_prd_generation.py`

**No modifications needed**:
- Method signature is sufficient: `process_discovery_answer(answer: str) -> str`
- Return value contains next question text (empty string if complete)
- Discovery status available via `get_discovery_status()` method
- Completion detection built-in (checks question index)

---

## Summary of Research Findings

| Question | Decision | Requires New Code | Complexity |
|----------|----------|-------------------|------------|
| **Storage** | Use memory table, category="discovery_answers" | ❌ No | Low - existing schema |
| **WebSocket** | Add 4 broadcast functions | ✅ Yes | Low - follow patterns |
| **Lead Agent** | Use existing process_discovery_answer() | ❌ No | Low - method complete |

### Updated Technical Context

The research answers all "NEEDS CLARIFICATION" items:

- **Storage**: `memory` table, category `"discovery_answers"` ✅
- **WebSocket**: Required - add 4 broadcast functions ✅
- **Lead Agent**: Existing method - use `process_discovery_answer()` ✅

### Implementation Impact

**Backend Work**:
- Create 1 API endpoint (POST /api/projects/:id/discovery/answer)
- Add 4 WebSocket broadcast functions
- **Total**: ~120 lines of code

**Frontend Work**:
- Modify DiscoveryProgress component (~200 lines)
- Subscribe to 4 WebSocket events
- **Total**: ~200 lines of code

**Testing Work**:
- 7 backend tests (endpoint + broadcasts)
- 13 frontend tests (UI interactions)
- 2 integration tests (full flow)
- **Total**: 22 tests

### Alternatives Considered

**Alternative 1: Skip WebSocket broadcasts**
- **Rejected**: Dashboard would not update in real-time
- **Why**: Inconsistent with existing architecture, poor UX

**Alternative 2: Create new Lead Agent method**
- **Rejected**: `process_discovery_answer()` already exists
- **Why**: Unnecessary duplication, adds complexity

**Alternative 3: Store answers in separate table**
- **Rejected**: memory table provides sufficient functionality
- **Why**: No migration needed, leverages existing methods

---

## Next Steps (Phase 1)

With all research questions answered, proceed to Phase 1 (Design & Contracts):

1. **Generate data-model.md**: Document discovery answer entities and relationships
2. **Generate contracts/**: Create OpenAPI spec for POST /api/projects/:id/discovery/answer
3. **Generate quickstart.md**: Document feature usage and integration points
4. **Update agent context**: Run `.specify/scripts/bash/update-agent-context.sh claude`

---

**Research Phase Complete**: All "NEEDS CLARIFICATION" items resolved ✅
**Gate Check**: Constitution compliance re-verified after research ✅
**Ready for Phase 1**: Design & Contracts generation
