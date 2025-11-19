# Quickstart: Discovery Answer UI Integration

**Feature**: 012-discovery-answer-ui
**Date**: 2025-11-19
**Audience**: Developers implementing or testing this feature

---

## Overview

This feature enables users to answer discovery questions through an interactive UI with real-time feedback. It adds answer submission capability to the existing `DiscoveryProgress` component.

**Key Components**:
- Frontend: Enhanced `DiscoveryProgress.tsx` with answer input UI
- Backend: POST `/api/projects/:id/discovery/answer` endpoint
- WebSocket: 4 broadcast events for real-time updates
- Database: Uses existing `memory` table with category `"discovery_answers"`

---

## Prerequisites

1. **Backend Running**:
   ```bash
   # Start FastAPI server
   uvicorn codeframe.ui.app:app --reload --port 8080
   ```

2. **Frontend Running**:
   ```bash
   # Start Next.js development server
   cd web-ui
   npm run dev
   ```

3. **Project in Discovery Phase**:
   ```python
   # Create project and start discovery
   project_id = await db.create_project(name="test-project", description="Test")
   lead_agent = LeadAgent(project_id=project_id)
   lead_agent.start_discovery()
   ```

---

## User Workflow

### Step 1: Navigate to Dashboard

```
Open browser: http://localhost:3000/projects/123
```

**What You See**:
- Dashboard with DiscoveryProgress component
- Current discovery question displayed
- Empty textarea with placeholder text
- Disabled submit button (no answer yet)
- Character counter: "0 / 5000 characters"

### Step 2: Type Answer

```
User types: "Build a task management system for remote teams"
```

**What Happens**:
- Character counter updates: "47 / 5000 characters"
- Submit button becomes enabled
- Textarea remains editable

### Step 3: Submit Answer

**Option A: Click Submit Button**
```
User clicks: "Submit Answer"
```

**Option B: Keyboard Shortcut**
```
User presses: Ctrl+Enter
```

**What Happens**:
1. Frontend validation checks (1-5000 chars)
2. Submit button shows "Submitting..."
3. Textarea and button disabled
4. POST request sent to `/api/projects/123/discovery/answer`
5. Backend processes answer via Lead Agent
6. WebSocket events broadcasted:
   - `discovery_answer_submitted`
   - `discovery_question_presented` (next question)
   - `discovery_progress_updated`
7. Success message shown: "Answer submitted! Loading next question..."
8. After 1 second:
   - Success message disappears
   - Next question displayed
   - Textarea cleared
   - Submit button re-enabled
   - Progress bar updates: 5% → 10%

### Step 4: Continue Until Complete

**Repeat Steps 2-3 for remaining questions**

When final question answered:
- `discovery_completed` WebSocket event broadcasted
- UI transitions to PRD generation phase
- Spinner shown: "Discovery complete! Generating PRD..."
- Progress bar: 100%

---

## API Integration

### Submit Answer (cURL Example)

```bash
curl -X POST http://localhost:8080/api/projects/123/discovery/answer \
  -H "Content-Type: application/json" \
  -d '{
    "answer": "Build a task management system for remote teams with real-time collaboration features."
  }'
```

**Success Response (200)**:
```json
{
  "success": true,
  "next_question": "What tech stack are you planning to use?",
  "is_complete": false,
  "current_index": 3,
  "total_questions": 20,
  "progress_percentage": 15.0
}
```

**Error Response (400 - Empty Answer)**:
```json
{
  "detail": "Answer must be between 1 and 5000 characters"
}
```

**Error Response (404 - Project Not Found)**:
```json
{
  "detail": "Project not found"
}
```

---

## WebSocket Integration

### Frontend Subscription

```typescript
// Subscribe to discovery events
const ws = new WebSocket('ws://localhost:8080/ws');

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);

  switch (message.type) {
    case 'discovery_answer_submitted':
      console.log('Answer submitted:', message.answer_preview);
      console.log('Progress:', message.progress.percentage + '%');
      break;

    case 'discovery_question_presented':
      console.log('Next question:', message.question_text);
      setCurrentQuestion(message.question_text);
      setProgress(message.current_index, message.total_questions);
      break;

    case 'discovery_progress_updated':
      console.log('Progress updated:', message.progress.percentage + '%');
      updateProgressBar(message.progress.percentage);
      break;

    case 'discovery_completed':
      console.log('Discovery complete! Total answers:', message.total_answers);
      console.log('Next phase:', message.next_phase);
      transitionToPRDGeneration();
      break;
  }
};
```

### Example WebSocket Messages

**Answer Submitted**:
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

**Next Question Presented**:
```json
{
  "type": "discovery_question_presented",
  "project_id": 123,
  "question_id": "q_tech_stack",
  "question_text": "What tech stack are you planning to use?",
  "current_index": 4,
  "total_questions": 20,
  "timestamp": "2025-11-19T14:30:01Z"
}
```

**Discovery Completed**:
```json
{
  "type": "discovery_completed",
  "project_id": 123,
  "total_answers": 20,
  "next_phase": "prd_generation",
  "timestamp": "2025-11-19T15:00:00Z"
}
```

---

## Testing

### Manual Testing Checklist

- [ ] **Submit Valid Answer**
  - Type answer (10-100 chars)
  - Click submit button
  - Verify success message appears
  - Verify next question displays
  - Verify progress bar updates

- [ ] **Keyboard Shortcut**
  - Type answer
  - Press Ctrl+Enter
  - Verify same behavior as clicking submit

- [ ] **Validation Errors**
  - Submit empty answer → Error: "Answer cannot be empty"
  - Submit whitespace-only answer → Error: "Answer must be between 1 and 5000 characters"
  - Type 5001 chars → Error: "Answer exceeds 5000 character limit"

- [ ] **Character Counter**
  - Type text → Verify counter updates
  - Type 4501 chars → Verify counter turns red
  - Delete text → Verify counter updates

- [ ] **Loading States**
  - Click submit → Verify button shows "Submitting..."
  - Verify textarea disabled during submission
  - Verify submit button disabled during submission

- [ ] **Progress Bar**
  - Submit answer → Verify progress bar animates to new percentage
  - Verify smooth transition (300ms duration)

- [ ] **Discovery Completion**
  - Answer all 20 questions
  - Verify discovery_completed event
  - Verify UI transitions to PRD generation
  - Verify spinner shown
  - Verify 100% progress

### Unit Testing (Jest)

```bash
# Run all DiscoveryProgress tests
cd web-ui
npm test -- src/components/__tests__/DiscoveryProgress.test.tsx

# Expected: 13 tests passing
# - Answer textarea renders
# - Character counter updates
# - Submit button disabled when answer empty
# - Submit button disabled during submission
# - Ctrl+Enter triggers submit
# - Validation error for empty answer
# - Validation error for answer > 5000 chars
# - Success message displays after submit
# - Error message displays on API failure
# - Answer cleared after successful submit
# - Progress bar updates after submit
# - Next question appears after submit
# - Discovery completion state (100% progress)
```

### Backend Testing (pytest)

```bash
# Run discovery endpoint tests
pytest tests/api/test_discovery_endpoints.py -v

# Expected: 7 tests passing
# - POST /api/projects/:id/discovery/answer success (200)
# - POST with empty answer returns 400
# - POST with answer > 5000 chars returns 400
# - POST with invalid project_id returns 404
# - POST when not in discovery phase returns 400
# - LeadAgent.process_discovery_answer() called correctly
# - Response includes next_question, is_complete, current_index
```

---

## Troubleshooting

### Issue: Submit Button Always Disabled

**Cause**: Answer validation failing (empty or whitespace-only)

**Solution**:
- Check answer.trim().length > 0
- Verify state updates correctly on textarea change
- Check console for validation errors

### Issue: No Next Question After Submit

**Cause**: API request failing or WebSocket not connected

**Solution**:
1. Check browser DevTools Network tab for API response
2. Verify WebSocket connection status: `ws.readyState === 1` (OPEN)
3. Check backend logs for errors
4. Verify Lead Agent is in "discovering" state

### Issue: Progress Bar Not Updating

**Cause**: WebSocket event not received or state not updating

**Solution**:
1. Check WebSocket messages in DevTools (WS tab)
2. Verify `discovery_progress_updated` event received
3. Check state management: `setDiscovery(newState)`
4. Verify progress calculation: `(current / total) * 100`

### Issue: Character Counter Shows Wrong Value

**Cause**: State not syncing with textarea value

**Solution**:
- Verify `onChange={(e) => setAnswer(e.target.value)}`
- Check `answer.length` calculation
- Ensure no debouncing delays

---

## Code Examples

### Frontend: Answer Submission Handler

```typescript
const submitAnswer = async () => {
  // Validation
  if (!answer.trim() || answer.length > 5000) {
    setError('Answer must be between 1 and 5000 characters');
    return;
  }

  // Start submission
  setIsSubmitting(true);
  setError(null);
  onSubmit?.();  // Parent shows loading spinner

  try {
    // API call
    const response = await fetch(
      `/api/projects/${projectId}/discovery/answer`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ answer: answer.trim() }),
      }
    );

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to submit answer');
    }

    // Success
    setSuccessMessage('Answer submitted! Loading next question...');
    setAnswer(''); // Clear input

    // Refresh discovery state after 1 second
    setTimeout(() => {
      fetchDiscoveryState();
      setSuccessMessage(null);
    }, 1000);

  } catch (err) {
    console.error('Failed to submit answer:', err);
    setError(err.message);
    onError?.(err);
  } finally {
    setIsSubmitting(false);
  }
};
```

### Backend: API Endpoint Implementation

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
    # Validate project
    project = await db.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    if project.phase != "discovery":
        raise HTTPException(400, "Project is not in discovery phase")

    # Get Lead Agent
    lead_agent = await get_lead_agent(project_id)

    # Process answer
    result_message = lead_agent.process_discovery_answer(answer.answer)

    # Get updated status
    status = lead_agent.get_discovery_status()

    # Broadcast WebSocket events
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

    # Return response
    return {
        "success": True,
        "next_question": status.get("current_question"),
        "is_complete": status["is_complete"],
        "current_index": status["current_question_index"],
        "total_questions": status["total_questions"],
        "progress_percentage": status["progress_percentage"],
    }
```

---

## Next Steps

After implementation:

1. **Run Tests**: Ensure all 20 tests passing (13 frontend + 7 backend)
2. **Manual Testing**: Complete full discovery session (20 questions)
3. **Code Review**: Verify TypeScript types, error handling, accessibility
4. **Documentation**: Update CLAUDE.md with new endpoint
5. **Merge**: Create PR with conventional commit message

**Ready for Implementation**: All design and planning complete ✅
