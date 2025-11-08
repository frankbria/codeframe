# Frontend Testing Checklist for Staging Server
**CodeFRAME Web UI - Human User Testing Guide**

**Staging URLs**:
- **Frontend**: http://codeframe.home.frankbria.net
- **API**: http://api.codeframe.home.frankbria.net
- **WebSocket**: ws://api.codeframe.home.frankbria.net/ws

**Last Updated**: 2025-10-19
**Sprint**: 3 Complete (Multi-agent execution with real-time updates)

**Note**: Port handling (3000 for frontend, 8000 for API) is managed by nginx reverse proxy.

---

## 🎯 Test Environment Setup

### Prerequisites
- Access to staging frontend: http://codeframe.home.frankbria.net
- API server accessible at: http://api.codeframe.home.frankbria.net
- WebSocket connection enabled at: ws://api.codeframe.home.frankbria.net/ws
- Sample project data in database
- Nginx reverse proxy handling port routing (3000→frontend, 8000→API)

### Connection Indicators
✅ **Look for**:
- Green "Live" indicator in header (WebSocket connected)
- Project status loads without errors
- Real-time updates appear in activity feed

---

## 1️⃣ **Project Management Features**

### 1.1 Project List View (`/`)
**API**: `GET /api/projects`

| Feature | Test Steps | Expected Behavior |
|---------|------------|-------------------|
| **Load Project List** | Navigate to homepage | Display all projects in grid layout |
| **Empty State** | View with no projects | Show "No projects yet" message with create button |
| **Project Cards** | Verify each project card | Shows name, status, phase, created date |
| **Click to Navigate** | Click any project card | Navigate to project dashboard `/projects/{id}` |
| **Loading State** | Refresh page | Shows "Loading projects..." before data loads |
| **Error Handling** | Disconnect backend | Shows "Failed to load projects" error message |

### 1.2 Project Creation Form
**API**: `POST /api/projects`

| Feature | Test Steps | Expected Behavior |
|---------|------------|-------------------|
| **Open Form** | Click "Create New Project" button | Form appears with name and type fields |
| **Close Form** | Click X button | Form disappears, returns to project list |
| **Enter Project Name** | Type project name (e.g., "Test Auth App") | Input accepts text, updates in real-time |
| **Select Project Type** | Choose from dropdown (python/javascript/typescript/java/go/rust) | Dropdown shows 6 options, allows selection |
| **Submit Empty Name** | Leave name blank, click Create | Shows error: "Project name cannot be empty" |
| **Submit Valid Form** | Fill name + type, click Create | Button shows "Creating...", then success message |
| **Success State** | After creation | Green checkmark, "Project created successfully" message |
| **Start Project Button** | Click "Start Project" after creation | Button shows "Starting...", navigates to dashboard |
| **Validation Feedback** | Try various invalid inputs | Appropriate error messages for each case |

---

## 2️⃣ **Dashboard Features** (`/projects/{id}`)

### 2.1 Header Section
**API**: `GET /api/projects/{id}/status`

| Feature | Test Steps | Expected Behavior |
|---------|------------|-------------------|
| **Project Title** | View header | Shows "CodeFRAME - {project name}" |
| **Status Badge** | Check status indicator | Green badge shows current status (ACTIVE, PAUSED, etc.) |
| **Phase Display** | View phase info | Shows "Phase: {phase} (Step X/15)" |
| **Live Indicator** | Watch WebSocket | Green pulsing dot + "Live" text when connected |
| **View PRD Button** | Click "View PRD" | Opens PRD modal with project requirements |
| **Chat Toggle** | Click "Chat with Lead" | Shows/hides chat interface below header |
| **Pause Button** | Click "Pause" | [Placeholder - not yet implemented] |

### 2.2 Discovery Progress (Sprint 2)
**API**: `GET /api/projects/{id}/discovery/progress`

| Feature | Test Steps | Expected Behavior |
|---------|------------|-------------------|
| **Idle State** | View before discovery starts | Shows "Discovery not started" in gray text |
| **Discovering State** | During Socratic questioning | Progress bar shows percentage, question count (e.g., "3/5") |
| **Current Question Display** | While discovering | Blue box shows category and current question text |
| **Auto-Refresh** | Wait during discovery | Updates every 10 seconds without page reload |
| **Completed State** | After discovery finishes | Green checkmark + "Discovery Complete" message |
| **Phase Indicator** | Check phase badge | Shows current phase (Discovery/Planning/Execution) |

### 2.3 Progress Section
**API**: `GET /api/projects/{id}/status`

| Feature | Test Steps | Expected Behavior |
|---------|------------|-------------------|
| **Task Progress** | View progress bar | Shows "X / Y tasks" with percentage |
| **Progress Bar** | Visual indicator | Blue bar fills to match percentage (0-100%) |
| **Real-time Updates** | Watch during execution | Progress updates without page reload (WebSocket) |
| **Time Tracking** | Check elapsed time | Shows hours elapsed (e.g., "2.5h") |
| **Remaining Estimate** | View estimate | Shows estimated remaining time (e.g., "~3.2h") |
| **Token Usage** | View cost tracking | Shows input tokens (M), output tokens (K) |
| **Cost Estimate** | View estimated cost | Shows dollar amount (e.g., "$1.23") |

### 2.4 Issues & Tasks Tree View (Sprint 2)
**API**: `GET /api/projects/{id}/issues`

| Feature | Test Steps | Expected Behavior |
|---------|------------|-------------------|
| **Issue List** | View issues section | Hierarchical tree with issue numbers (e.g., "1.5") |
| **Expand/Collapse** | Click ▶ or ▼ icon | Toggles task visibility under issue |
| **Issue Status Badge** | View issue badges | Color-coded status (green=completed, blue=in_progress, etc.) |
| **Priority Badge** | Check priority | Color-coded (red=1, orange=2, yellow=3, gray=4) |
| **Provenance Icon** | Check 🤖 or 👤 icons | Shows who proposed (agent vs human) |
| **Task Numbers** | View task hierarchy | Shows nested numbers (e.g., "1.5.3" under "1.5") |
| **Task Dependencies** | Check "Depends on" | Shows dependent issue/task numbers |
| **Task Description** | Expand task | Shows description text if available |
| **Empty State** | View with no issues | Shows "No issues available" message |

### 2.5 Agent Status Section
**API**: `GET /api/projects/{id}/agents`

| Feature | Test Steps | Expected Behavior |
|---------|------------|-------------------|
| **Agent List** | View agents | Shows all agents (Lead, Backend, Frontend, Test, Review) |
| **Status Indicator** | Check colored dots | Green=working, Red=blocked, Yellow=idle |
| **Agent Type** | View agent labels | Shows type (e.g., "Backend Agent") |
| **Provider Display** | Check provider | Shows in parentheses (e.g., "(claude)") |
| **Maturity Badge** | View maturity | Gray badge shows level (directive/coaching/supporting/delegating) |
| **Current Task** | Agent working | Shows "Task #X: {title}" with progress percentage |
| **Blocker Display** | Agent blocked | Red warning: "⚠️ {blocker reason}" |
| **Context Tokens** | View token usage | Shows agent's context usage in K tokens |
| **Real-time Updates** | Watch during work | Agent status updates via WebSocket |

### 2.6 Blockers / Pending Questions
**API**: `GET /api/projects/{id}/blockers`

| Feature | Test Steps | Expected Behavior |
|---------|------------|-------------------|
| **Section Visibility** | Check when blockers exist | Section appears only when blockers present |
| **Blocker Card** | View blocker details | Shows question, reason, blocking agents |
| **Severity Badge** | Check severity | Red="SYNC", Yellow="ASYNC" |
| **Task Reference** | View task ID | Shows "Task #X" linked to blocker |
| **Answer Button** | Click "Answer Now" | [Placeholder - answer interface not fully implemented] |
| **Multiple Blockers** | View with 2+ blockers | All blockers listed separately |

### 2.7 Recent Activity Feed
**API**: `GET /api/projects/{id}/activity`

| Feature | Test Steps | Expected Behavior |
|---------|------------|-------------------|
| **Activity List** | View activity | Chronological list (newest first) |
| **Timestamps** | Check time display | Shows HH:MM:SS format |
| **Activity Icons** | View event types | ✅=completed, 🧪=tests, ⚠️=blocker, ✓=resolved |
| **Agent Attribution** | Check agent name | Shows which agent performed action |
| **Test Results** | After test run | Shows "✅ All tests passed (X/Y)" or "⚠️ Tests failed" |
| **Git Commits** | After code commit | Shows "📝 {message} ({hash})" with short hash |
| **Self-Correction** | During retry | Shows "🔄 Self-correction attempt X/3" |
| **Real-time Updates** | During execution | New activities appear without page reload (WebSocket) |
| **Activity Limit** | Scroll through | Shows up to 50 recent items |

---

## 3️⃣ **Chat Interface** (Sprint 2: cf-14.2)

### 3.1 Chat Visibility
**Component**: `ChatInterface.tsx`

| Feature | Test Steps | Expected Behavior |
|---------|------------|-------------------|
| **Toggle Chat** | Click "Chat with Lead" button | Chat appears/disappears below header |
| **Chat Height** | View chat interface | Fixed height of 500px with scroll |
| **Persistent State** | Toggle off and on | Chat state preserved during session |

### 3.2 Message Display
**API**: `GET /api/projects/{id}/chat/history`

| Feature | Test Steps | Expected Behavior |
|---------|------------|-------------------|
| **Load History** | Open chat | Previous messages load from history |
| **Empty State** | No messages | Shows "No messages yet. Start a conversation!" |
| **User Messages** | View your messages | Right-aligned, blue background |
| **Assistant Messages** | View agent responses | Left-aligned, gray background |
| **Message Timestamps** | Check time display | Shows relative time (e.g., "2 minutes ago") |
| **Auto-Scroll** | Send new message | Automatically scrolls to bottom |
| **Long Messages** | Send paragraph text | Messages wrap properly, maintain formatting |
| **History Error** | Backend unavailable | Red banner: "Failed to load chat history" |

### 3.3 Message Sending
**API**: `POST /api/projects/{id}/chat`

| Feature | Test Steps | Expected Behavior |
|---------|------------|-------------------|
| **Type Message** | Enter text in input | Input accepts text, no character limit visible |
| **Send Button State** | Empty input | Button disabled (gray) |
| **Send Button Active** | Type text | Button enabled (blue) |
| **Submit with Enter** | Press Enter key | Sends message (same as click Send) |
| **Submit with Click** | Click "Send" button | Sends message to API |
| **Sending State** | After submit | Button shows spinner + "Sending..." |
| **Optimistic Update** | Send message | User message appears immediately |
| **Assistant Response** | Wait for reply | Assistant message appears below user's |
| **Error Handling** | Backend error | Error banner appears, message removed, input restored |
| **Agent Offline** | Agent not running | Input disabled, shows "Agent offline" placeholder |
| **Focus Management** | After send | Input focus returns for next message |

### 3.4 WebSocket Integration
**WebSocket**: `/ws`

| Feature | Test Steps | Expected Behavior |
|---------|------------|-------------------|
| **Real-time Messages** | Agent sends message independently | Message appears without user action |
| **Message Format** | Check WebSocket message | Contains role, content, timestamp |
| **Multi-user Sync** | Open two browser tabs | Messages sync across tabs in real-time |

---

## 4️⃣ **PRD Modal** (Sprint 2: cf-26)

### 4.1 Modal Display
**API**: `GET /api/projects/{id}/prd`

| Feature | Test Steps | Expected Behavior |
|---------|------------|-------------------|
| **Open Modal** | Click "View PRD" button | Modal overlay appears with PRD content |
| **Close Modal** | Click X or outside modal | Modal disappears, returns to dashboard |
| **Modal Size** | View modal | Large modal with scroll if content overflows |
| **Loading State** | While fetching | Shows loading indicator |
| **Error State** | PRD not available | Shows error message in modal |

### 4.2 PRD Content Display

| Feature | Test Steps | Expected Behavior |
|---------|------------|-------------------|
| **Title Section** | View PRD header | Shows project name and description |
| **Executive Summary** | Check summary | Displays problem statement and solution overview |
| **User Stories** | View stories | Bulleted list of user stories |
| **Features** | Check feature list | Structured list of features with descriptions |
| **Technical Requirements** | View tech specs | Shows tech stack, architecture, constraints |
| **Success Metrics** | Check metrics | Displays measurable success criteria |
| **Markdown Rendering** | View formatting | Proper rendering of headings, lists, bold, italic |

---

## 5️⃣ **Real-Time WebSocket Updates** (Sprint 3: cf-45)

### 5.1 WebSocket Connection
**Endpoint**: `ws://api.codeframe.home.frankbria.net/ws`

| Feature | Test Steps | Expected Behavior |
|---------|------------|-------------------|
| **Auto-Connect** | Load any project page | WebSocket connects automatically |
| **Connection Indicator** | Check header | Green pulsing dot + "Live" text appears |
| **Reconnection** | Disconnect network, reconnect | Auto-reconnects within seconds |
| **Project Subscription** | Open project | Subscribes to project-specific events |

### 5.2 Real-Time Event Types

| Event Type | Test Steps | Expected Behavior |
|------------|------------|-------------------|
| **task_status_changed** | Watch task execution | Task status updates in tree view without reload |
| **agent_status_changed** | Watch agent work | Agent status dot changes color in real-time |
| **test_result** | Run tests | Activity feed shows "✅ All tests passed" or failure |
| **commit_created** | Code committed | Activity feed shows "📝 {message} ({hash})" |
| **correction_attempt** | Self-correction triggered | Activity feed shows "🔄 Self-correction attempt X/3" |
| **progress_update** | Task completes | Progress bar updates without page reload |
| **activity_update** | General activity | New item added to Recent Activity feed |
| **status_update** | Project status changes | Full project data refreshes |
| **blocker_resolved** | Answer blocker | Blocker list refreshes |

### 5.3 Event Filtering

| Feature | Test Steps | Expected Behavior |
|---------|------------|-------------------|
| **Project Filtering** | Open multiple projects | Each page only shows its project's events |
| **Event Deduplication** | Rapid events | No duplicate updates, smooth transitions |

---

## 6️⃣ **Navigation & Routing**

### 6.1 URL Routing

| Route | Test Steps | Expected Behavior |
|-------|------------|-------------------|
| `/` | Navigate to root | Shows project list page |
| `/projects/{id}` | Navigate to project | Shows project dashboard |
| **Invalid Project ID** | `/projects/99999` | Shows error or redirects to project list |
| **Browser Back** | Click back button | Returns to previous page correctly |
| **Direct URL** | Enter URL in browser | Loads page directly without navigation |

### 6.2 State Management

| Feature | Test Steps | Expected Behavior |
|---------|------------|-------------------|
| **SWR Caching** | Navigate away and back | Data loads from cache instantly |
| **Auto-Revalidation** | Leave tab open 5+ minutes | Data refreshes on focus |
| **Optimistic Updates** | Create project, send chat | UI updates before API confirms |

---

## 7️⃣ **Error Handling & Edge Cases**

### 7.1 API Error Scenarios

| Scenario | Test Steps | Expected Behavior |
|----------|------------|-------------------|
| **Backend Offline** | Stop API server | All endpoints show appropriate error messages |
| **Slow Network** | Throttle network to 3G | Loading states appear, no crashes |
| **401 Unauthorized** | Invalid auth (future) | Redirects to login or shows auth error |
| **500 Server Error** | Trigger backend error | Shows "An error occurred" with retry option |
| **Network Timeout** | Block requests | Shows timeout error after delay |

### 7.2 WebSocket Error Scenarios

| Scenario | Test Steps | Expected Behavior |
|----------|------------|-------------------|
| **Connection Failed** | Block WebSocket port | "Live" indicator disappears, polling fallback |
| **Connection Lost** | Disconnect during session | Attempts reconnection, shows offline state |
| **Reconnection** | Restore connection | "Live" indicator returns, data syncs |

### 7.3 UI Edge Cases

| Scenario | Test Steps | Expected Behavior |
|----------|------------|-------------------|
| **Long Project Names** | Create project with 100+ char name | Name truncates or wraps properly |
| **Special Characters** | Use emojis, symbols in input | Handles gracefully, displays correctly |
| **Rapid Clicking** | Click buttons repeatedly | Prevents duplicate requests, shows loading |
| **Browser Resize** | Change window size | Responsive layout adjusts properly |
| **Mobile View** | View on phone/tablet | Mobile-friendly layout (if implemented) |

---

## 8️⃣ **Performance & Accessibility**

### 8.1 Performance Metrics

| Metric | Test Steps | Expected Behavior |
|--------|------------|-------------------|
| **Initial Load** | Measure page load time | < 3 seconds on first load |
| **Navigation Speed** | Click between pages | < 500ms transition |
| **WebSocket Latency** | Send chat message | Response within 1-2 seconds |
| **Memory Usage** | Leave dashboard open 1 hour | No significant memory leaks |
| **CPU Usage** | Monitor during activity | Stays under 20% on modern hardware |

### 8.2 Accessibility

| Feature | Test Steps | Expected Behavior |
|---------|------------|-------------------|
| **Keyboard Navigation** | Tab through interface | All interactive elements reachable |
| **Focus Indicators** | Tab to buttons/inputs | Visible focus rings appear |
| **ARIA Labels** | Screen reader test | Proper labels for all controls |
| **Color Contrast** | Check status badges | Meets WCAG AA standards |
| **Alt Text** | Check images/icons | Descriptive alternative text provided |

---

## 9️⃣ **Cross-Browser Compatibility**

### 9.1 Browser Testing

| Browser | Test | Expected Behavior |
|---------|------|-------------------|
| **Chrome** | Full feature test | All features work perfectly |
| **Firefox** | Full feature test | All features work perfectly |
| **Safari** | Full feature test | All features work (WebSocket compatible) |
| **Edge** | Full feature test | All features work perfectly |

### 9.2 Device Testing

| Device | Test | Expected Behavior |
|--------|------|-------------------|
| **Desktop** | 1920x1080 resolution | Full layout displays properly |
| **Tablet** | iPad Pro | Responsive layout adjusts |
| **Mobile** | iPhone/Android | Mobile-friendly (if implemented) |

---

## 🐛 **Known Issues & Limitations**

### Current Limitations (Sprint 3)
1. **Pause button**: Placeholder only, not functional yet
2. **Answer blocker**: Button visible but handler not fully implemented
3. **Mobile optimization**: Desktop-focused, mobile may need improvement
4. **Authentication**: No login system yet (future sprint)
5. **Multi-user**: No user accounts, shared project state

### Expected Bugs to Report
- WebSocket disconnection recovery edge cases
- Long message history performance degradation
- Task tree view deep nesting display issues
- Real-time update race conditions

---

## ✅ **Testing Workflow Recommendation**

### Quick Smoke Test (15 minutes)
1. Load homepage → Verify project list
2. Create new project → Verify creation + start
3. Open dashboard → Check all sections load
4. Toggle chat → Send 1-2 messages
5. Watch for real-time updates → Verify WebSocket working

### Comprehensive Test (60 minutes)
1. **Project Management** (10 min): Create, list, navigate
2. **Discovery Flow** (10 min): Test Socratic questioning progress
3. **Dashboard Components** (15 min): All sections + real-time updates
4. **Chat Interface** (10 min): Full conversation flow
5. **PRD Modal** (5 min): Open, view, close
6. **Error Scenarios** (10 min): Disconnect backend, test recovery

### Stress Test (30 minutes)
1. Create 10+ projects → Test list performance
2. Send 50+ chat messages → Test scroll + history
3. Leave dashboard open 30 min → Monitor WebSocket stability
4. Rapid navigation → Test state management

---

## 📊 **Success Criteria Summary**

| Category | Passing Criteria |
|----------|------------------|
| **Project Management** | Can create, view, navigate projects without errors |
| **Dashboard** | All 7 sections display correct data in real-time |
| **Chat** | Send/receive messages with proper error handling |
| **PRD** | View formatted requirements document |
| **WebSocket** | Real-time updates appear within 2 seconds |
| **Error Handling** | Graceful degradation, no crashes |
| **Performance** | < 3s initial load, smooth interactions |
| **Accessibility** | Keyboard navigable, screen reader friendly |

---

## 📝 **Bug Report Template**

```markdown
**Title**: [Short description]
**Severity**: Critical / High / Medium / Low
**Steps to Reproduce**:
1.
2.
3.

**Expected Behavior**:
**Actual Behavior**:
**Browser**: Chrome/Firefox/Safari (version)
**URL**:
**Screenshots**: [If applicable]
**Console Errors**: [If any]
```

---

**End of Testing Checklist**
For questions or to report issues, contact the development team.
