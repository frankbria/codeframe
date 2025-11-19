# Data Model: Discovery Answer UI Integration

**Feature**: 012-discovery-answer-ui
**Date**: 2025-11-19
**Phase**: 1 (Design & Contracts)

---

## Overview

This feature uses existing database schema (`memory` table) for discovery answer persistence. No new tables or migrations required.

---

## Entities

### 1. DiscoveryAnswer (Backend - Pydantic)

**Purpose**: Validate incoming discovery answer submissions from frontend

**Location**: `codeframe/ui/app.py` (inline) or `codeframe/core/models.py`

**Schema**:
```python
from pydantic import BaseModel, Field, field_validator

class DiscoveryAnswer(BaseModel):
    """Request model for discovery answer submission."""

    answer: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="User's answer to the current discovery question"
    )

    @field_validator('answer')
    @classmethod
    def validate_answer(cls, v: str) -> str:
        """Ensure answer is not empty after trimming."""
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("Answer cannot be empty or whitespace only")
        if len(trimmed) > 5000:
            raise ValueError("Answer cannot exceed 5000 characters")
        return trimmed
```

**Validation Rules**:
- Required field (not nullable)
- Min length: 1 character (after trimming)
- Max length: 5000 characters
- Whitespace-only answers rejected
- Automatic trimming before validation

---

### 2. DiscoveryAnswerResponse (Backend - Pydantic)

**Purpose**: Standardized API response after answer submission

**Location**: `codeframe/ui/app.py` (inline) or `codeframe/core/models.py`

**Schema**:
```python
from typing import Optional
from pydantic import BaseModel, Field

class DiscoveryAnswerResponse(BaseModel):
    """Response model for discovery answer submission."""

    success: bool = Field(
        ...,
        description="Whether the answer was successfully processed"
    )

    next_question: Optional[str] = Field(
        None,
        description="Next discovery question text (null if discovery complete)"
    )

    is_complete: bool = Field(
        ...,
        description="Whether discovery phase is complete"
    )

    current_index: int = Field(
        ...,
        ge=0,
        description="Current question index (0-based)"
    )

    total_questions: int = Field(
        ...,
        gt=0,
        description="Total number of discovery questions"
    )

    progress_percentage: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Discovery completion percentage (0.0 - 100.0)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "next_question": "What tech stack are you planning to use?",
                "is_complete": False,
                "current_index": 3,
                "total_questions": 20,
                "progress_percentage": 15.0
            }
        }
```

**State Transitions**:
- `is_complete = False` → More questions remaining
- `is_complete = True` → Discovery finished, PRD generation starts
- `next_question = null` when `is_complete = True`

---

### 3. DiscoveryState (Frontend - TypeScript)

**Purpose**: Client-side representation of discovery progress

**Location**: `web-ui/src/types/discovery.ts`

**Schema**:
```typescript
export interface DiscoveryState {
  /** Current phase: discovering | prd_generation | complete */
  phase: 'discovering' | 'prd_generation' | 'complete';

  /** Current question being presented to user */
  currentQuestion: string | null;

  /** Unique identifier for current question */
  currentQuestionId: string | null;

  /** Current question number (1-based for display) */
  currentQuestionIndex: number;

  /** Total number of questions in discovery */
  totalQuestions: number;

  /** Number of questions answered so far */
  answeredCount: number;

  /** Discovery completion percentage (0-100) */
  progressPercentage: number;

  /** Whether all questions have been answered */
  isComplete: boolean;
}

export interface DiscoveryAnswer {
  /** User's answer text */
  answer: string;
}

export interface DiscoveryProgressProps {
  /** Project ID for API calls */
  projectId: number;

  /** Refresh interval in milliseconds (default: 5000) */
  refreshInterval?: number;
}
```

**Frontend State Management**:
```typescript
// Component state
const [discovery, setDiscovery] = useState<DiscoveryState | null>(null);
const [answer, setAnswer] = useState('');
const [isSubmitting, setIsSubmitting] = useState(false);
const [error, setError] = useState<string | null>(null);
const [successMessage, setSuccessMessage] = useState<string | null>(null);
```

---

### 4. Memory Table (Database - Existing)

**Purpose**: Persistent storage for discovery answers

**Location**: SQLite database (`.codeframe/state.db`)

**Schema** (from `codeframe/persistence/database.py:193-206`):
```sql
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

**Discovery Answer Records**:
```sql
-- Example discovery answer
INSERT INTO memory (project_id, category, key, value) VALUES (
    123,
    'discovery_answers',
    'q_project_problem',
    'Build a task management system for remote teams'
);
```

**Query Patterns**:
```python
# Get all discovery answers for a project
answers = db.get_project_memories(
    project_id=123,
    category="discovery_answers"
)

# Get specific answer
answer = db.get_memory(
    project_id=123,
    category="discovery_answers",
    key="q_project_problem"
)

# Create new answer
db.create_memory(
    project_id=123,
    category="discovery_answers",
    key="q_target_users",
    value="Developers building web applications"
)
```

---

## Entity Relationships

```
┌─────────────────────┐
│  Projects Table     │
│  (id, phase, ...)   │
└──────────┬──────────┘
           │ 1
           │
           │ *
┌──────────▼──────────────────────────────────┐
│  Memory Table                               │
│  - id (PK)                                  │
│  - project_id (FK → projects.id)            │
│  - category = 'discovery_answers'           │
│  - key = question_id (e.g., 'q_problem')    │
│  - value = answer text                      │
│  - created_at, updated_at                   │
└─────────────────────────────────────────────┘
           │
           │ read/write
           │
┌──────────▼──────────┐
│  Lead Agent         │
│  - process_discovery│
│    _answer()        │
│  - get_discovery    │
│    _status()        │
└─────────────────────┘
           │
           │ HTTP API
           │
┌──────────▼──────────────────────┐
│  POST /api/projects/:id/        │
│       discovery/answer          │
│  Request: DiscoveryAnswer       │
│  Response: DiscoveryAnswerResp  │
└─────────────────────────────────┘
           │
           │ WebSocket
           │
┌──────────▼──────────────────────┐
│  WebSocket Broadcasts           │
│  - discovery_answer_submitted   │
│  - discovery_question_presented │
│  - discovery_progress_updated   │
│  - discovery_completed          │
└─────────────────────────────────┘
           │
           │ subscribe
           │
┌──────────▼──────────────────────┐
│  Frontend (React)               │
│  - DiscoveryProgress component  │
│  - DiscoveryState management    │
│  - WebSocket event handlers     │
└─────────────────────────────────┘
```

---

## State Machine

### Discovery Phase States

```
┌──────────────┐
│  init        │ User creates project
└──────┬───────┘
       │
       │ start_discovery()
       ▼
┌──────────────────┐
│  discovering     │ User answers questions
│  (phase)         │
└──────┬───────────┘
       │
       │ For each question:
       │ - User submits answer
       │ - process_discovery_answer(answer)
       │ - Returns next question
       │
       │ Loop until current_index >= total_questions
       │
       ▼
┌──────────────────┐
│  complete        │ All questions answered
│  (phase)         │
└──────┬───────────┘
       │
       │ generate_prd()
       ▼
┌──────────────────┐
│  prd_generation  │ Creating PRD document
│  (phase)         │
└──────┬───────────┘
       │
       │ PRD created
       ▼
┌──────────────────┐
│  planning        │ Project moves to planning phase
│  (phase)         │
└──────────────────┘
```

### Answer Submission Flow

```
User types answer in textarea
       │
       ▼
User clicks Submit OR presses Ctrl+Enter
       │
       ▼
Frontend validation (1-5000 chars)
       │
       ├─ FAIL → Show error message
       │
       └─ PASS
           │
           ▼
    POST /api/projects/:id/discovery/answer
    { answer: "trimmed text" }
           │
           ▼
    Backend validation (Pydantic)
           │
           ├─ FAIL → 400 error
           │
           └─ PASS
               │
               ▼
        lead_agent.process_discovery_answer(answer)
               │
               ├─ Save to memory table
               ├─ Increment question index
               ├─ Check completion
               │
               ▼
        get_discovery_status()
               │
               ▼
        Broadcast WebSocket events
        ├─ discovery_answer_submitted
        ├─ discovery_question_presented (if not complete)
        └─ discovery_completed (if complete)
               │
               ▼
        Return DiscoveryAnswerResponse
        {
          success: true,
          next_question: "...",
          is_complete: false,
          current_index: 3,
          total_questions: 20,
          progress_percentage: 15.0
        }
               │
               ▼
    Frontend receives response
               │
               ├─ Clear answer input
               ├─ Show success message
               ├─ Update progress bar
               ├─ Display next question
               └─ (OR) Transition to PRD generation if complete
```

---

## Validation Rules

### Frontend Validation

**Answer Text**:
- Min length: 1 character (after trim)
- Max length: 5000 characters
- Cannot be empty or whitespace-only
- Character counter warning at >4500 chars

**Submit Button**:
- Disabled when: `answer.trim().length === 0`
- Disabled when: `isSubmitting === true`
- Enabled when: `answer.trim().length > 0 && !isSubmitting`

### Backend Validation

**Pydantic Model** (`DiscoveryAnswer`):
- Field required (not null, not undefined)
- Min length: 1 (after trim)
- Max length: 5000
- Automatic whitespace trimming
- ValueError if validation fails

**Business Logic Validation**:
- Project must exist (`404` if not found)
- Project phase must be `"discovery"` (`400` if not)
- Discovery state must be `"discovering"` (not `"complete"`)

---

## Performance Considerations

### Database Queries

**Optimizations**:
- Use `project_id` index for fast lookups
- Use composite index on `(project_id, category)` for discovery answers
- Limit query results with `LIMIT` clause

**Expected Load**:
- 20 questions per project (typical)
- 20 INSERT operations per discovery session
- 1 SELECT per answer submission (to get next question)
- Low write frequency (human typing speed ~1 answer/minute)

### API Response Time

**Target**: <2 seconds end-to-end

**Breakdown**:
- Frontend validation: <16ms (60fps)
- Network latency: ~50-200ms
- Backend processing: ~100-500ms
  - Pydantic validation: <10ms
  - Database write: <50ms
  - Lead Agent processing: <100ms
  - WebSocket broadcast: <50ms
- Frontend update: <100ms

**LLM Processing**: If Lead Agent uses LLM to generate next question, add +1-2 seconds

---

## Error Handling

### HTTP Error Codes

| Code | Scenario | Response Body |
|------|----------|---------------|
| `200` | Success | `DiscoveryAnswerResponse` |
| `400` | Validation failure | `{ detail: "Answer must be between 1 and 5000 characters" }` |
| `400` | Wrong phase | `{ detail: "Project is not in discovery phase" }` |
| `404` | Project not found | `{ detail: "Project not found" }` |
| `500` | Server error | `{ detail: "Internal server error" }` |

### Frontend Error States

**Validation Errors** (client-side):
- Empty answer: "Answer cannot be empty"
- Too long: "Answer exceeds 5000 character limit"
- Display in red box below submit button
- Keep answer in textarea (don't clear)
- Re-enable submit button after fixing

**API Errors** (server-side):
- 400/422: Display `error.detail` message
- 500: "Server error occurred. Please try again."
- Network failure: "Failed to submit answer. Please check your connection."
- Display in red box below submit button
- Keep answer in textarea (allow retry)

---

## WebSocket Message Formats

See [contracts/websocket.yaml](./contracts/websocket.yaml) for complete schemas.

**Example - Answer Submitted**:
```json
{
  "type": "discovery_answer_submitted",
  "project_id": 123,
  "question_id": "q_target_users",
  "answer_preview": "Developers building web applications...",
  "progress": {
    "current": 3,
    "total": 20,
    "percentage": 15.0
  },
  "timestamp": "2025-11-19T14:30:00Z"
}
```

---

## Data Flow Summary

1. **User Input** → Frontend validation → Submit button enabled
2. **Submit** → POST /api/projects/:id/discovery/answer → Backend validation
3. **Backend** → Lead Agent processes → Saves to memory table
4. **Completion Check** → If complete: discovery_completed, else: next question
5. **WebSocket** → Broadcast events → Frontend updates in real-time
6. **Response** → Frontend displays next question → Clear input → Update progress

---

**Data Model Phase Complete** ✅
**Next Step**: Generate API contracts (OpenAPI specification)
