# Feature Specification: Discovery Answer UI Integration

**Feature ID**: 012-discovery-answer-ui
**Sprint**: 9.5 - Critical UX Fixes
**Priority**: P0 - CRITICAL WORKFLOW
**Effort**: 6 hours
**Branch**: 012-discovery-answer-ui

---

## Problem Statement

### Current Behavior (BROKEN UX)

Users can see discovery questions but cannot answer them:

```
Dashboard → DiscoveryProgress component shows:
"Current Question: What problem does your project solve?"
↓
User sees question (read-only display)
↓
NO input field, NO submit button
↓
User confused: "Where do I type my answer?"
↓
User gives up (8/10 UX complexity score)
```

### Expected Behavior

```
Dashboard → DiscoveryProgress shows:
"Question 2 of 20: What problem does your project solve?"
↓
Textarea with placeholder: "Type your answer here..."
↓
Character counter: "0 / 5000 characters"
↓
Submit button enabled when answer > 0 chars
↓
User types answer → clicks Submit OR Ctrl+Enter
↓
POST /api/projects/:id/discovery/answer
↓
Success message: "Answer submitted! Loading next question..."
↓
Next question appears (1 second delay)
↓
Progress bar updates: 10% → 15%
```

### Impact

**Severity**: SHOWSTOPPER - Discovery phase is completely unusable without this feature.

**Users Affected**: 100% of new users attempting to use CodeFRAME for the first time.

**Business Impact**: Without answer input, users cannot complete the discovery phase, making the entire product unusable for its primary workflow.

---

## User Stories

### US1: Answer Input Field (P1 - CRITICAL)

**As a** new user creating a project
**I want to** see an answer textarea below the current discovery question
**So that** I can type my response to the AI agent's question

**Acceptance Criteria**:
- ✅ Textarea renders below current question display
- ✅ Placeholder text: "Type your answer here... (Ctrl+Enter to submit)"
- ✅ 6 rows tall by default
- ✅ Resizing disabled (resize-none class)
- ✅ Full width of container
- ✅ `maxLength={5000}` attribute enforced
- ✅ Focused state: blue ring (focus:ring-2 focus:ring-blue-500)
- ✅ Disabled state: gray background when isSubmitting=true
- ✅ Error state: red border when validation fails

**Technical Notes**:
- Component: `web-ui/src/components/DiscoveryProgress.tsx`
- State: `const [answer, setAnswer] = useState('')`
- Validation: 1-5000 characters

---

### US2: Character Counter (P1 - CRITICAL)

**As a** user typing an answer
**I want to** see a character counter showing current/max length
**So that** I know how much I can write and avoid exceeding the limit

**Acceptance Criteria**:
- ✅ Counter displays: "{count} / 5000 characters"
- ✅ Updates in real-time as user types
- ✅ Color changes to red when > 4500 characters (warning)
- ✅ Positioned below textarea, left-aligned
- ✅ Text size: text-sm
- ✅ Default color: text-gray-500
- ✅ Warning color: text-red-600

**Technical Notes**:
- Value: `answer.length`
- Conditional styling: `answer.length > 4500 ? 'text-red-600' : 'text-gray-500'`

---

### US3: Submit Button (P1 - CRITICAL)

**As a** user who has typed an answer
**I want to** click a "Submit Answer" button
**So that** I can send my response to the AI agent and move to the next question

**Acceptance Criteria**:
- ✅ Button text: "Submit Answer" (default) or "Submitting..." (loading)
- ✅ Positioned to the right of character counter
- ✅ Enabled when `answer.trim().length > 0`
- ✅ Disabled when `answer.trim().length === 0` or `isSubmitting === true`
- ✅ Disabled state: gray background (bg-gray-400), no hover
- ✅ Enabled state: blue background (bg-blue-600), hover:bg-blue-700
- ✅ Rounded corners: rounded-lg
- ✅ Padding: py-2 px-6
- ✅ Font weight: font-semibold

**Technical Notes**:
- onClick handler: `submitAnswer()`
- Disabled logic: `disabled={isSubmitting || !answer.trim()}`

---

### US4: Keyboard Shortcut (P2 - ENHANCEMENT)

**As a** power user typing answers
**I want to** press Ctrl+Enter to submit my answer
**So that** I can complete discovery faster without using the mouse

**Acceptance Criteria**:
- ✅ Ctrl+Enter triggers submit (same as button click)
- ✅ Works only when textarea is focused
- ✅ Does NOT submit if answer is empty
- ✅ Hint text below textarea: "💡 Tip: Press [Ctrl+Enter] to submit"
- ✅ Hint text size: text-xs
- ✅ Hint text color: text-gray-500
- ✅ Centered alignment: text-center
- ✅ `<kbd>` styling: px-2 py-1 bg-gray-100 border border-gray-300 rounded

**Technical Notes**:
- Event handler: `onKeyDown={handleKeyPress}`
- Check: `e.ctrlKey && e.key === 'Enter'`
- Call: `submitAnswer()`

---

### US5: Answer Submission (P1 - CRITICAL)

**As a** user clicking submit
**I want to** send my answer to the backend API
**So that** the Lead Agent can process it and generate the next question

**Acceptance Criteria**:
- ✅ POST request to `/api/projects/:id/discovery/answer`
- ✅ Request body: `{ answer: answer.trim() }`
- ✅ Content-Type: application/json
- ✅ Loading state: `isSubmitting = true` before API call
- ✅ All inputs disabled during submission (textarea + button)
- ✅ Success handling: clear answer, show success message, refresh state
- ✅ Error handling: show error message, keep answer, re-enable inputs
- ✅ Response expected: `{ success: true, next_question, is_complete, current_index }`

**Technical Notes**:
- API client: Use `fetch()` (no abstraction needed for POST)
- Error states: 400 (validation), 404 (project not found), 500 (server error)
- Success flow: `setSuccessMessage()` → wait 1s → `fetchDiscoveryState()` → clear message

---

### US6: Success Message (P1 - CRITICAL)

**As a** user who submitted an answer
**I want to** see a confirmation message
**So that** I know my answer was saved successfully

**Acceptance Criteria**:
- ✅ Message text: "Answer submitted! Loading next question..."
- ✅ Background: bg-green-50
- ✅ Border: border border-green-200
- ✅ Text color: text-green-800
- ✅ Padding: p-3
- ✅ Rounded corners: rounded-lg
- ✅ Display duration: 1 second
- ✅ Auto-dismiss after discovery state refreshes
- ✅ Position: Below submit button, above keyboard hint

**Technical Notes**:
- State: `const [successMessage, setSuccessMessage] = useState<string | null>(null)`
- Timing: `setTimeout(() => { fetchDiscoveryState(); setSuccessMessage(null); }, 1000)`

---

### US7: Error Handling (P1 - CRITICAL)

**As a** user experiencing submission errors
**I want to** see clear error messages
**So that** I understand what went wrong and can retry

**Acceptance Criteria**:
- ✅ Validation error: "Answer must be between 1 and 5000 characters"
- ✅ API error (400): Display backend error message
- ✅ API error (500): "Server error occurred. Please try again."
- ✅ Network error: "Failed to submit answer. Please check your connection."
- ✅ Error background: bg-red-50
- ✅ Error border: border border-red-200
- ✅ Error text color: text-red-800
- ✅ Error padding: p-3
- ✅ Error rounded corners: rounded-lg
- ✅ Position: Below submit button, above keyboard hint
- ✅ Textarea red border when error present
- ✅ Answer preserved when error occurs (not cleared)

**Technical Notes**:
- State: `const [error, setError] = useState<string | null>(null)`
- Validation: Check before API call
- API errors: Parse `response.json().detail` or use generic message
- Network errors: Catch in try/catch block

---

### US8: Progress Bar Update (P1 - CRITICAL)

**As a** user submitting answers
**I want to** see the progress bar update after each answer
**So that** I understand how far through discovery I am

**Acceptance Criteria**:
- ✅ Progress bar width: `(currentIndex / totalQuestions) * 100%`
- ✅ Progress percentage text: `Math.round((currentIndex / totalQuestions) * 100)`
- ✅ Smooth transition: transition-all duration-300
- ✅ Updates automatically after successful submission
- ✅ Question counter updates: "2 of 20" → "3 of 20"
- ✅ No page reload required (SPA behavior)

**Technical Notes**:
- Data source: `fetchDiscoveryState()` after submit
- Updates: `setDiscovery(updatedData)` triggers re-render
- Existing component: Progress bar already exists, just needs refresh

---

### US9: Next Question Display (P1 - CRITICAL)

**As a** user who completed an answer
**I want to** see the next question appear automatically
**So that** I can continue the discovery process seamlessly

**Acceptance Criteria**:
- ✅ Next question appears 1 second after success message
- ✅ Previous answer is cleared from textarea
- ✅ Textarea remains focused (optional UX enhancement)
- ✅ Question number increments: "Question 2" → "Question 3"
- ✅ New question text replaces old question
- ✅ No page refresh or navigation
- ✅ Smooth transition (no flashing)

**Technical Notes**:
- Trigger: `fetchDiscoveryState()` called after 1s delay
- Update: `setDiscovery(newState)` updates UI
- Clear input: `setAnswer('')` after success
- Focus management: Optional `textareaRef.current?.focus()`

---

### US10: Discovery Completion (P2 - ENHANCEMENT)

**As a** user answering the final question
**I want to** see a completion state instead of another question
**So that** I know discovery is finished and PRD generation is starting

**Acceptance Criteria**:
- ✅ When `is_complete === true`, hide answer UI
- ✅ Show loading spinner (size: lg)
- ✅ Show message: "Discovery complete! Generating PRD..."
- ✅ Progress bar: 100% width
- ✅ Percentage: "100% complete"
- ✅ Centered layout: text-center py-8
- ✅ Spinner from existing component: `<Spinner size="lg" />`

**Technical Notes**:
- Condition: `discovery?.phase === 'prd_generation'`
- This state likely already exists in DiscoveryProgress component
- No API changes needed (backend already handles this)

---

## Backend Requirements

### API Endpoint: POST /api/projects/:id/discovery/answer

**Request**:
```json
{
  "answer": "string (1-5000 chars, trimmed)"
}
```

**Response (Success - 200)**:
```json
{
  "success": true,
  "next_question": "What tech stack are you planning to use?",
  "is_complete": false,
  "current_index": 3,
  "total_questions": 20
}
```

**Response (Completion - 200)**:
```json
{
  "success": true,
  "next_question": null,
  "is_complete": true,
  "current_index": 20,
  "total_questions": 20
}
```

**Response (Validation Error - 400)**:
```json
{
  "detail": "Answer must be between 1 and 5000 characters"
}
```

**Response (Not Found - 404)**:
```json
{
  "detail": "Project not found"
}
```

**Response (Wrong Phase - 400)**:
```json
{
  "detail": "Project is not in discovery phase"
}
```

**Backend Implementation** (`codeframe/ui/app.py`):
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

    # Validate answer length
    if not answer.answer.strip() or len(answer.answer) > 5000:
        raise HTTPException(400, "Answer must be between 1 and 5000 characters")

    # Get Lead Agent
    lead_agent = await get_lead_agent(project_id)

    # Process answer
    result = await lead_agent.process_discovery_answer(answer.answer)

    # Return updated state
    return {
        "success": True,
        "next_question": result.next_question,
        "is_complete": result.is_complete,
        "current_index": result.current_index,
        "total_questions": result.total_questions,
    }
```

---

## Non-Functional Requirements

### Performance
- Answer submission response time: < 2 seconds (includes LLM processing)
- UI updates after submission: < 100ms
- Character counter updates: No perceptible lag (<16ms for 60fps)
- Progress bar animation: 300ms smooth transition

### Accessibility
- Textarea must have proper `aria-label` or associated `<label>`
- Error messages must have `role="alert"` for screen readers
- Success messages must have `role="status"` for screen readers
- Keyboard shortcut must be discoverable (hint text provided)
- Focus management: Return focus to textarea after submission

### Security
- Answer length validated client-side AND server-side
- HTML/XSS sanitization handled by React (automatic)
- No API key exposure in frontend code
- Rate limiting on backend (prevent spam submissions)

### Browser Compatibility
- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+
- Mobile browsers: iOS Safari 14+, Chrome Mobile 90+

---

## Out of Scope

The following are explicitly NOT included in this feature:

- ❌ Editing previous answers (future feature)
- ❌ Saving draft answers (auto-save)
- ❌ Rich text formatting in answers
- ❌ File attachments in answers
- ❌ Voice-to-text input
- ❌ Multi-language support
- ❌ Answer templates or suggestions
- ❌ AI-powered answer validation
- ❌ Collaborative discovery (multiple users)
- ❌ Answer history/audit trail

---

## Success Metrics

### Qualitative
- ✅ Users can complete discovery without confusion
- ✅ Answer submission feels responsive (<2s)
- ✅ Error messages are clear and actionable
- ✅ Keyboard shortcut improves power user efficiency

### Quantitative
- ✅ 100% of discovery sessions can submit answers
- ✅ < 5% error rate on answer submissions
- ✅ Average time per question: 1-3 minutes
- ✅ Discovery completion rate: > 80%

---

## Dependencies

### Existing Components
- ✅ `DiscoveryProgress.tsx` - Already exists, needs enhancement
- ✅ `Spinner.tsx` - Already exists (created in Feature 2)
- ✅ Dashboard layout - Already exists

### Backend
- ⚠️ `/api/projects/:id/discovery/answer` endpoint - **NEEDS TO BE CREATED**
- ⚠️ `LeadAgent.process_discovery_answer()` method - **NEEDS TO BE CREATED**
- ✅ Discovery state tracking - Already exists (assumed)

### Types
- ⚠️ `DiscoveryState` interface - Needs to be defined/updated
- ⚠️ `DiscoveryAnswer` Pydantic model - Needs to be created

---

## Testing Requirements

### Unit Tests (Jest/Vitest)
- [ ] Answer textarea renders with correct attributes
- [ ] Character counter updates as user types
- [ ] Submit button disabled when answer empty
- [ ] Submit button disabled during submission
- [ ] Keyboard shortcut (Ctrl+Enter) triggers submit
- [ ] Validation error for empty answer
- [ ] Validation error for answer > 5000 chars
- [ ] Success message displays after successful submit
- [ ] Error message displays on API failure
- [ ] Answer cleared after successful submit
- [ ] Progress bar updates after submit
- [ ] Next question appears after submit
- [ ] Discovery completion state (100% progress)

### Integration Tests
- [ ] Full submission flow: type → submit → next question
- [ ] Error recovery: error → fix → successful retry
- [ ] Multiple answers in sequence (3+ questions)
- [ ] Discovery completion flow (final answer → PRD generation)

### Backend Tests (pytest)
- [ ] POST /api/projects/:id/discovery/answer success (200)
- [ ] POST with empty answer returns 400
- [ ] POST with answer > 5000 chars returns 400
- [ ] POST with invalid project_id returns 404
- [ ] POST when not in discovery phase returns 400
- [ ] LeadAgent.process_discovery_answer() called correctly
- [ ] Response includes next_question, is_complete, current_index

### Manual Testing
- [ ] Type answer and click submit button
- [ ] Type answer and press Ctrl+Enter
- [ ] Submit empty answer (should show error)
- [ ] Submit very long answer (>5000 chars, should show error)
- [ ] Network failure scenario (disconnect, should show error)
- [ ] Complete full discovery session (20 questions)
- [ ] Mobile responsiveness (textarea, button, layout)

---

## Risk Assessment

### High Risk
- **Backend endpoint missing**: If `/api/projects/:id/discovery/answer` doesn't exist, frontend will be blocked
  - **Mitigation**: Create backend endpoint first, stub if Lead Agent integration complex

### Medium Risk
- **Discovery state management**: Complex interaction between frontend and Lead Agent
  - **Mitigation**: Start with minimal implementation, hardcode next question if needed
  - **Fallback**: Make submission one-way (no validation, basic acknowledgment)

### Low Risk
- **UI implementation**: Standard form validation and state management
- **Testing**: Jest patterns well-established from Feature 2

---

## Implementation Order

1. **Backend First** (2 hours):
   - Create `DiscoveryAnswer` Pydantic model
   - Create `/api/projects/:id/discovery/answer` endpoint
   - Add basic validation (length, project exists, phase check)
   - Stub Lead Agent integration if complex
   - Write backend tests (7 tests)

2. **Frontend Core** (2 hours):
   - Add answer state management to DiscoveryProgress
   - Create textarea with validation
   - Create submit button with loading states
   - Add character counter
   - Add keyboard shortcut (Ctrl+Enter)

3. **Frontend Polish** (1 hour):
   - Add success/error message display
   - Add progress bar update logic
   - Add next question display logic
   - Add discovery completion state

4. **Testing** (1 hour):
   - Write 13 frontend unit tests
   - Write 2 integration tests
   - Manual testing (full discovery flow)

---

## File Changes Summary

### New Files
- None (all modifications to existing files)

### Modified Files
- `web-ui/src/components/DiscoveryProgress.tsx` - Add answer input UI and submission logic
- `codeframe/ui/app.py` - Add POST /api/projects/:id/discovery/answer endpoint
- `web-ui/src/types/discovery.ts` - Add/update DiscoveryState interface (if needed)
- `web-ui/src/components/__tests__/DiscoveryProgress.test.tsx` - Add 13 unit tests
- `codeframe/tests/api/test_discovery_endpoints.py` - Add 7 backend tests

### Estimated Lines of Code
- Frontend: ~200 lines (100 implementation + 100 tests)
- Backend: ~80 lines (40 implementation + 40 tests)
- **Total**: ~280 lines

---

**Status**: READY FOR PLANNING
**Next Step**: Run `/speckit.plan` to generate implementation plan
