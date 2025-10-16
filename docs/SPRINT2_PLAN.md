# Sprint 2: Socratic Discovery - Implementation Plan

**Sprint Duration**: Week 2
**Sprint Goal**: Enable Lead Agent to conduct intelligent requirements gathering through Socratic dialogue
**Status**: 🚀 **READY TO START**

---

## 🎯 Sprint Objectives

### Primary Goal
Build a conversational interface that allows the Lead Agent to guide users through a Socratic discovery process, capturing requirements and generating structured project plans.

### User Story
> **As a developer**, I want the Lead Agent to ask me questions about my project goals, understand my requirements through conversation, generate a comprehensive PRD, and show it in the dashboard so I can review and approve the project plan before development begins.

### Success Criteria
- ✅ Lead Agent conducts Socratic dialogue with contextual follow-up questions
- ✅ User responses are captured and structured in database
- ✅ Agent generates comprehensive PRD from conversation
- ✅ PRD is viewable in dashboard
- ✅ Basic task list generated from PRD
- ✅ All interactions work through chat interface with real-time updates

---

## 📋 Implementation Tasks

### cf-14: Chat Interface & API Integration (P0)
**Owner**: Full-stack
**Dependencies**: Sprint 1 (cf-10 WebSocket, cf-9 Lead Agent)
**Estimated Effort**: 8-10 hours

#### Subtasks

**cf-14.1: Backend Chat API Endpoints** (3-4 hours)
- Implement `POST /api/projects/{id}/chat`
  - Accept user message
  - Route to Lead Agent
  - Return AI response
  - Broadcast via WebSocket
- Implement `GET /api/projects/{id}/chat/history`
  - Retrieve conversation from database
  - Return chronological message list
  - Support pagination (limit/offset)
- Error handling
  - 404: Project not found
  - 400: Empty message
  - 500: Agent communication failure
- **Tests**: 12 test cases
  - Chat endpoint success
  - Message validation
  - History retrieval
  - WebSocket broadcasting
  - Error handling (4 cases)
  - Integration workflows

**cf-14.2: Frontend Chat Component** (4-5 hours)
- Create `ChatInterface.tsx` component
  - Message input field
  - Send button with loading state
  - Message history display
  - Auto-scroll to latest message
  - Message timestamps
- Integrate with Dashboard
  - Place in main content area
  - Show/hide based on agent status
  - Handle WebSocket updates
- Real-time message updates
  - Subscribe to WebSocket
  - Append new messages
  - Update UI instantly
- **Tests**: 8 UI component tests
  - Message rendering
  - Send functionality
  - WebSocket integration
  - Loading states

**cf-14.3: Message Persistence** (1 hour)
- Use existing `memory` table with `category='conversation'`
- Ensure messages stored with:
  - `role`: "user" or "assistant"
  - `key`: "user" or "assistant"
  - `value`: message content
  - `created_at`: timestamp
- **Tests**: Covered by existing database tests

**Definition of Done**:
- ✅ Can send chat messages via API
- ✅ Messages appear in frontend instantly
- ✅ Conversation history persists and loads
- ✅ WebSocket updates work in real-time
- ✅ 20 tests passing (12 backend + 8 frontend)
- ✅ Chat interface integrated in dashboard

---

### cf-15: Socratic Discovery Flow (P0)
**Owner**: AI/Agent Logic
**Dependencies**: cf-14 (Chat API)
**Estimated Effort**: 10-12 hours

#### Subtasks

**cf-15.1: Discovery Question Framework** (4-5 hours)
- Create `SocraticDiscovery` class
  - Predefined question templates
  - Context-aware follow-up generation
  - Question sequencing logic
- Question categories:
  - **Problem**: What problem does this solve?
  - **Users**: Who are the primary users?
  - **Features**: What are the core features?
  - **Tech Stack**: Any specific technology requirements?
  - **Constraints**: Timeline, budget, scale considerations?
- Implement question flow:
  - Start with broad questions
  - Ask follow-ups based on answers
  - Know when to move to next category
  - Detect completion (sufficient info gathered)
- **Tests**: 15 test cases
  - Question generation
  - Context awareness
  - Flow sequencing
  - Completion detection

**cf-15.2: Answer Capture & Structuring** (3-4 hours)
- Store Q&A pairs in `memory` table
  - `category='discovery'`
  - `key`: question category
  - `value`: JSON with {question, answer, timestamp}
- Build requirement structure from answers
  - Extract key requirements
  - Identify features
  - Capture constraints
  - Detect patterns
- **Tests**: 10 test cases
  - Answer storage
  - Structure building
  - Pattern detection

**cf-15.3: Lead Agent Discovery Integration** (3 hours)
- Modify `LeadAgent.chat()` to:
  - Detect if project in discovery phase
  - Use SocraticDiscovery for questions
  - Capture structured answers
  - Transition to PRD generation when complete
- State management:
  - Track discovery progress
  - Store in project metadata
  - Update project status
- **Tests**: 12 test cases
  - Discovery mode detection
  - Question routing
  - State transitions
  - Integration workflows

**Definition of Done**:
- ✅ Agent asks contextual discovery questions
- ✅ Follow-up questions adapt to user responses
- ✅ Q&A pairs stored structurally
- ✅ Discovery completes when sufficient info gathered
- ✅ 37 tests passing
- ✅ Discovery flow integrated with chat

---

### cf-16: PRD Generation & Task Decomposition (P0)
**Owner**: AI/Agent Logic
**Dependencies**: cf-15 (Discovery complete)
**Estimated Effort**: 8-10 hours

#### Subtasks

**cf-16.1: PRD Generation from Discovery** (4-5 hours)
- Implement `generate_prd()` method
  - Load all discovery Q&A
  - Send to Claude with PRD template
  - Structure PRD document
  - Save to `.codeframe/memory/prd.md`
- PRD structure:
  - Executive Summary
  - Problem Statement
  - User Personas
  - Features & Requirements
  - Technical Architecture (basic)
  - Success Metrics
  - Timeline & Milestones
- Claude prompt engineering:
  - Clear PRD template
  - Structured output format
  - Include all discovery insights
- **Tests**: 10 test cases
  - PRD generation
  - Content completeness
  - File persistence
  - Error handling

**cf-16.2: Basic Task Decomposition** (3-4 hours)
- Implement `decompose_prd()` method
  - Parse PRD for features
  - Generate task list
  - Create task records in `tasks` table
  - Set basic dependencies
- Task structure:
  - `title`: Short description
  - `description`: Detailed spec
  - `dependencies`: List of task IDs
  - `status`: 'pending'
  - `assigned_to`: null (unassigned)
- **Tests**: 12 test cases
  - Task extraction
  - Dependency detection
  - Database storage
  - Validation

**cf-16.3: PRD & Task Dashboard Display** (1-2 hours)
- Add PRD viewer to dashboard
  - "View PRD" button
  - Modal or separate page
  - Markdown rendering
- Add task list view
  - Show all tasks
  - Display dependencies
  - Basic status indicators
- **Tests**: 6 UI component tests
  - PRD display
  - Task list rendering

**Definition of Done**:
- ✅ PRD generated from discovery
- ✅ PRD saved to file system
- ✅ Tasks created in database
- ✅ PRD viewable in dashboard
- ✅ Task list displayed
- ✅ 28 tests passing

---

### cf-17: Discovery State Management (P1)
**Owner**: Backend/State
**Dependencies**: cf-15, cf-16
**Estimated Effort**: 4-5 hours

#### Subtasks

**cf-17.1: Project Phase Tracking** (2-3 hours)
- Add `phase` field to projects table
  - Values: 'discovery', 'planning', 'active', 'review', 'complete'
  - Default: 'discovery'
- Update project phase automatically:
  - Start: 'discovery'
  - Discovery complete: 'planning'
  - Tasks generated: 'active'
- **Tests**: 8 test cases
  - Phase transitions
  - Status persistence
  - Integration workflows

**cf-17.2: Progress Indicators** (2 hours)
- Track discovery progress
  - Questions asked / remaining
  - Categories covered
  - Completion percentage
- Display in dashboard
  - Progress bar
  - Current phase indicator
  - Next steps hint
- **Tests**: 6 test cases
  - Progress calculation
  - UI updates

**Definition of Done**:
- ✅ Project phases tracked accurately
- ✅ Phase transitions automatic
- ✅ Progress visible in dashboard
- ✅ 14 tests passing

---

## 🧪 Testing Strategy

### Test Coverage Targets
- **Backend API**: >90% coverage
- **Discovery Logic**: 100% coverage (critical path)
- **PRD Generation**: >85% coverage
- **Frontend Components**: >80% coverage

### Test Categories

**Unit Tests** (85 tests estimated):
- Chat API endpoints (12)
- Discovery question logic (15)
- Answer structuring (10)
- PRD generation (10)
- Task decomposition (12)
- Phase management (8)
- UI components (14)
- Integration helpers (4)

**Integration Tests** (20 tests estimated):
- End-to-end discovery flow (5)
- Chat → Discovery → PRD → Tasks (4)
- WebSocket broadcasting (3)
- State transitions (4)
- Error recovery (4)

**E2E Tests** (5 tests estimated):
- Complete discovery session (1)
- PRD generation and viewing (1)
- Task list display (1)
- Multi-user scenarios (1)
- Error scenarios (1)

**Total Expected Tests**: ~110 tests

### TDD Approach
- RED: Write failing test first
- GREEN: Implement minimal code to pass
- REFACTOR: Clean up and optimize
- Document: Add docstrings and comments
- Commit: Small, focused commits

---

## 📊 Sprint 2 Implementation Roadmap

### Week 2 Execution Plan

**Day 1-2: Chat Foundation** (cf-14)
1. Implement backend chat API (cf-14.1)
2. Build frontend chat component (cf-14.2)
3. Test message persistence (cf-14.3)
4. **Milestone**: Working chat interface

**Day 3-4: Discovery Logic** (cf-15)
5. Build Socratic discovery framework (cf-15.1)
6. Implement answer capture (cf-15.2)
7. Integrate with Lead Agent (cf-15.3)
8. **Milestone**: Agent asks contextual questions

**Day 5-6: PRD & Tasks** (cf-16)
9. Implement PRD generation (cf-16.1)
10. Add task decomposition (cf-16.2)
11. Build dashboard viewers (cf-16.3)
12. **Milestone**: PRD and tasks generated

**Day 7: State & Polish** (cf-17)
13. Add phase tracking (cf-17.1)
14. Implement progress indicators (cf-17.2)
15. Integration testing
16. Bug fixes and refinements
17. **Milestone**: Complete Sprint 2 demo ready

**Total Effort Estimate**: 30-37 hours

**Critical Path**: cf-14 → cf-15 → cf-16
**Parallel Work**: cf-17 can start after cf-15

---

## 🎬 Demo Script

### Sprint 2 Demo Workflow

```bash
# Terminal 1: Start Backend
python -m codeframe.ui.server

# Terminal 2: Start Frontend
cd web-ui && npm run dev

# Browser: http://localhost:14100
```

### Demo Steps

**1. Project Creation & Start**
```bash
# Create project via API
curl -X POST http://localhost:14200/api/projects \
  -H "Content-Type: application/json" \
  -d '{"project_name": "AI SaaS Platform", "project_type": "python"}'

# Start Lead Agent
curl -X POST http://localhost:14200/api/projects/1/start
```

**2. Socratic Discovery**
```
Browser: http://localhost:14100

Lead Agent: "Hi! I'm here to help you plan your project. Let's start with some questions..."

Lead Agent: "What problem does your project solve?"

User: "I want to build a SaaS platform for AI-powered document analysis"

Lead Agent: "Great! Who are the primary users of this platform?"

User: "Legal professionals and enterprise compliance teams"

Lead Agent: "What are the core features you envision?"

User: "Document upload, AI analysis, compliance checking, report generation"

Lead Agent: "Any specific technology requirements or preferences?"

User: "Python backend, React frontend, needs to be scalable"

Lead Agent: "Got it! Let me summarize what we've discussed..."
[Displays summary]

Lead Agent: "Does this capture your vision? (yes/no)"

User: "yes"

Lead Agent: "Perfect! I'm now generating your PRD..."
[Progress indicator shows]

Lead Agent: "✅ PRD complete! Generating tasks..."
[Task generation progress]

Lead Agent: "✅ Created 42 tasks with dependencies. Ready to review!"
```

**3. View PRD & Tasks**
```
Dashboard shows:
- Phase: "Planning → Active"
- Progress: "Discovery complete"
- [View PRD] button
- Task List: 42 tasks organized by phase
- Dependencies visualized

Click "View PRD":
- Modal opens
- Shows formatted PRD with all sections
- Can download as PDF
- Can edit/approve

Click "Tasks":
- Shows all 42 tasks
- Dependency graph visible
- Ready to assign to agents
```

**Demo Success Metrics**:
- Discovery takes 3-5 minutes of conversation
- PRD generates in <30 seconds
- Tasks created in <20 seconds
- Dashboard updates in real-time
- Everything persists (refresh browser to verify)

---

## 🎯 Definition of Done - Sprint 2

### Functional Requirements
- ✅ Working chat interface with message history
- ✅ Lead Agent conducts Socratic discovery
- ✅ Questions adapt to user responses
- ✅ PRD generated from conversation
- ✅ PRD saved and viewable in dashboard
- ✅ Basic task list created from PRD
- ✅ All interactions in real-time via WebSocket

### Technical Requirements
- ✅ ~110 tests passing (unit + integration + e2e)
- ✅ >85% test coverage on core logic
- ✅ TDD compliance (100% of features)
- ✅ Clean code with documentation
- ✅ No performance degradation (<2s response time)

### User Experience
- ✅ Intuitive chat interface
- ✅ Clear progress indicators
- ✅ Helpful error messages
- ✅ PRD is professional quality
- ✅ Dashboard updates feel instant

### Sprint Review Readiness
- ✅ Demo runs successfully end-to-end
- ✅ All code committed to main branch
- ✅ Beads issues closed
- ✅ Documentation updated
- ✅ No critical bugs in demo path

---

## 🔍 Sprint 2 Scope Boundaries

### IN SCOPE (Must have for demo):
- Basic Socratic questioning with 4-5 question categories
- PRD generation with key sections
- Basic task list (title, description, dependencies)
- Chat interface in dashboard
- Real-time updates via WebSocket

### OUT OF SCOPE (Defer to later sprints):
- ❌ Advanced question generation (AI-powered follow-ups) - Sprint 3
- ❌ Task priority scoring - Sprint 3
- ❌ Detailed dependency graphs - Sprint 4
- ❌ Task estimation - Sprint 4
- ❌ PRD editing capabilities - Sprint 5
- ❌ Multi-user collaboration - Sprint 12
- ❌ PRD templates - Future
- ❌ Export to external tools - Future

### NICE TO HAVE (If time permits):
- Streaming responses from Claude for PRD generation
- PRD syntax highlighting and formatting
- Basic task search/filter
- Discovery conversation export
- Dark mode for chat interface

---

## 📈 Success Metrics

### Technical Metrics
- **Test Pass Rate**: 100% (target: ~110 tests)
- **Test Coverage**: >85% overall, 100% on discovery logic
- **API Response Time**: <500ms (p95) for chat
- **PRD Generation**: <30 seconds
- **Task Generation**: <20 seconds
- **WebSocket Latency**: <100ms

### Functional Metrics
- **Discovery Questions**: 4-5 categories covered
- **PRD Quality**: All required sections present
- **Task Count**: 30-50 tasks generated
- **Dependency Accuracy**: >90% of dependencies correct

### User Experience Metrics
- **Setup Time**: <2 minutes to complete discovery
- **Chat Responsiveness**: Messages appear instantly
- **Error Rate**: <5% during normal usage
- **Demo Success**: 100% - demo must work flawlessly

---

## 🚀 Getting Started

### Prerequisites
- Sprint 1 complete (foundation infrastructure)
- All Sprint 1 tests passing (111 tests)
- Backend running on port 14200
- Frontend running on port 14100
- Staging server operational

### Day 1 Setup
1. Create Sprint 2 branch: `git checkout -b sprint-2-socratic-discovery`
2. Create beads issues for all tasks (cf-14 through cf-17)
3. Set up test files structure
4. Review AGILE_SPRINTS.md Sprint 2 section
5. Begin cf-14.1 (Backend Chat API)

---

## 📝 Notes & Considerations

### Key Technical Decisions
- **Question Framework**: Start with predefined templates, evolve to dynamic generation in Sprint 3
- **PRD Format**: Use markdown for flexibility and readability
- **Task Schema**: Keep simple for Sprint 2, enhance in Sprint 3-4
- **State Machine**: Project phases guide agent behavior

### Risks & Mitigations
- **Risk**: PRD quality inconsistent
  - **Mitigation**: Well-crafted Claude prompts with examples, validation checks
- **Risk**: Discovery takes too long
  - **Mitigation**: Limit to 4-5 question categories, smart completion detection
- **Risk**: Task decomposition produces too many/few tasks
  - **Mitigation**: Set reasonable bounds (30-50 tasks), validate before saving

### Dependencies on Sprint 1
- WebSocket infrastructure (cf-10.4)
- Lead Agent chat method (cf-9.3)
- Database memory table (cf-8.1)
- Project lifecycle management (cf-10)
- Frontend Dashboard component structure

---

## 🔄 Sprint Ceremonies

### Sprint Planning (Monday)
- Review this plan document
- Create beads issues
- Assign priorities
- Estimate effort for each subtask

### Daily Progress Check
- Update TodoWrite for tracking
- Review test pass rate
- Address any blockers immediately
- Adjust scope if needed

### Mid-Sprint Review (Wednesday)
- Demo current progress
- Is demo still achievable?
- Any scope adjustments needed?
- Risk assessment

### Sprint Review (Friday)
- **DEMO TIME** - Run complete Sprint 2 demo
- Record demo (recommended)
- Document what worked/what didn't
- Identify improvements for Sprint 3

### Sprint Retrospective (Friday)
- What went well?
- What could be better?
- Technical learnings
- Process improvements for Sprint 3

---

**Sprint 2 Status**: 🚀 Ready to Start
**Expected Completion**: End of Week 2
**Next Sprint**: Sprint 3 - Single Agent Execution

---

*This plan is a living document. Adjust scope and priorities as needed to ensure a successful demo at sprint end.*
