# codeframe Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-01-03

## Documentation Navigation

**For efficient documentation navigation**, see [AGENTS.md](AGENTS.md).

Quick reference:
- **Current sprint**: [SPRINTS.md](SPRINTS.md) (sprint timeline index)
- **Sprint details**: `sprints/sprint-NN-name.md` (individual sprint summaries)
- **Feature specs**: `specs/{feature}/` (detailed implementation guides)
- **Architecture**: [CODEFRAME_SPEC.md](CODEFRAME_SPEC.md) (system design)
- **Feature Docs**:
  - [Context Management](docs/context-management.md) - Tiered memory system (HOT/WARM/COLD)
  - [Session Lifecycle](docs/session-lifecycle.md) - Auto-save/restore CLI sessions
  - [Sprint 10: Quality Gates & Metrics](docs/sprint-10-review-polish.md) - Quality enforcement, checkpoints, cost tracking
  - [E2E Testing](docs/e2e-testing.md) - Playwright + TestSprite testing guide

## Documentation Structure

- **`sprints/`** - Sprint execution records (WHAT was delivered WHEN)
- **`specs/`** - Feature implementation specifications (HOW to implement)
- **`docs/`** - Feature-specific documentation (detailed usage guides)
- **Root** - Project-wide documentation (coding standards, architecture)

## Active Technologies
- Python 3.11+ (backend), TypeScript 5.3+ (frontend)
- FastAPI, AsyncAnthropic, React 18, Next.js 14, Tailwind CSS
- SQLite with async support (aiosqlite)
- tiktoken (token counting), TestSprite (E2E test generation)
- WebSockets for real-time updates

## Project Structure
```
/
├── sprints/          # Sprint summaries (80-120 lines each)
├── specs/            # Feature specifications (400-800 lines each)
├── docs/             # Feature documentation (see Navigation above)
├── codeframe/        # Python package
├── web-ui/           # React frontend
└── tests/            # Test suite
```

NOTE: This is a pre-production application with a flattened v1.0 database schema. The schema uses direct table creation with no migration system.

## Commands
```bash
uv run pytest                              # Run all tests
uv run pytest tests/test_*worker_agent.py  # Worker agent tests (async)
uv run ruff check .                        # Lint code
cd web-ui && npm test                      # Frontend tests
cd web-ui && npm run build                 # Frontend build
```

## Context Management for AI Conversations

### Quality-First Development
See `.claude/rules.md` for comprehensive context management guidelines including:
- **Token budget**: ~50,000 tokens per conversation (warning at 45k)
- **Checkpoint system**: Every 5 AI responses
- **Auto-reset triggers**: Quality degradation >10%, response count >15-20, token budget >45k
- **Context handoff template**: For smooth conversation resets

### Quality Monitoring
Use `scripts/quality-ratchet.py` to track quality metrics:
```bash
# Check current quality (auto-suggests reset if degradation detected)
python scripts/quality-ratchet.py check

# Record baseline metrics
python scripts/quality-ratchet.py record --coverage 87.5 --pass-rate 100.0 --response-count 5

# View quality trends
python scripts/quality-ratchet.py show
```

**Auto-suggestion**: When quality degrades >10%, the tool recommends context reset with handoff template from `.claude/rules.md`.

## Recent Changes

- **Authentication Migration to FastAPI Users** (2026-01-02): Complete auth system overhaul
  * **Migration**: BetterAuth → FastAPI Users with JWT tokens
  * **Auth Required**: Authentication is now mandatory (no bypass mode)
  * **Token Storage**: `localStorage.getItem('auth_token')` for frontend
  * **WebSocket Auth**: Requires `?token=TOKEN` query parameter
  * **New Module**: `codeframe/auth/` with dependencies, manager, models, router, schemas
  * **Deleted**: `web-ui/src/lib/auth.ts`, `web-ui/src/lib/auth-client.ts`
  * **Documentation**: See [docs/authentication.md](docs/authentication.md)

- **Auto-Start Discovery on Project Creation** (2026-01-03): UX improvement
  * **Behavior**: Discovery process now starts automatically after project creation
  * **Manual Start**: "Start Discovery" button added to DiscoveryProgress for idle projects
  * **Loading States**: Dynamic messages ("Creating project..." → "Starting discovery...")
  * **Files**: `web-ui/src/app/page.tsx`, `web-ui/src/components/DiscoveryProgress.tsx`

- **Dashboard Tab Refactoring** (2026-01-03): Improved navigation
  * **New Tabs**: Tasks, Quality Gates, Metrics as dedicated top-level tabs
  * **Structure**: Review findings moved to Tasks tab, Quality Gates separate tab
  * **File**: `web-ui/src/components/Dashboard.tsx`

- **CI/CD Environment Variable Fixes** (2026-01-03): Production deployment fixes
  * **Issue**: `NEXT_PUBLIC_*` vars must be set at build time for Next.js
  * **Fix**: Export env vars before `npm run build` in deploy workflow
  * **WebSocket**: Fixed auth token inclusion in connection URL
  * **API URLs**: Fixed hardcoded `localhost:8002` in `agentAssignment.ts`

- **Database Repository Refactoring** (2025-12-22): Refactored monolithic Database class into modular repository architecture
  * **Architecture**: Repository pattern with 17 domain-specific repositories
  * **Code Reduction**: Database class reduced from 4,531 lines to 301 lines (93.4% reduction)
  * **Maintainability**: Each repository handles a single domain (150-530 lines each)
  * **Backward Compatibility**: 100% - all existing imports and method signatures preserved
  * **Testing**: 71/71 tests passing (100% pass rate)
  * **Structure**: `persistence/database.py` (facade) + `schema_manager.py` + `repositories/` (17 repos)
  * **Documentation**: See `docs/architecture/database-repository-pattern.md` for details

- **shadcn/ui Nova Migration** (2025-12-23): Migrated web-ui to Nova design system
  * **Status**: Complete - All 40+ components updated
  * **Icon Library**: Replaced lucide-react with Hugeicons (@hugeicons/react)
  * **Color System**: Migrated to semantic Nova palette (bg-card, text-foreground, etc.)
  * **Testing**: 1164 tests passing (10 test failures remaining in component tests)
  * **Build**: ✅ Passing with no TypeScript errors
  * **Documentation**: See "UI Template Configuration" section below

- **Sprint 10: Review & Polish** (2025-11-23): MVP COMPLETE! 🎉
  * **Quality Gates**: Multi-stage pre-completion checks (tests → type → coverage → review)
  * **Checkpoint & Recovery**: Git + SQLite + context snapshots for project state rollback
  * **Metrics & Cost Tracking**: Real-time token usage and cost analytics
  * **E2E Testing**: TestSprite + Playwright for comprehensive workflow validation
  * **Details**: See [docs/sprint-10-review-polish.md](docs/sprint-10-review-polish.md)

- **Context Management System** (007-context-management): Intelligent tiered memory (HOT/WARM/COLD)
  * **Token Reduction**: 30-50% reduction through strategic archival
  * **Importance Scoring**: Hybrid exponential decay algorithm
  * **Flash Save**: Automatic checkpointing before context compactification
  * **Details**: See [docs/context-management.md](docs/context-management.md)

- **Session Lifecycle Management** (014-session-lifecycle): Auto-save/restore work context across CLI restarts
  * **Storage**: File-based (`.codeframe/session_state.json`)
  * **Details**: See [docs/session-lifecycle.md](docs/session-lifecycle.md)

<!-- MANUAL ADDITIONS START -->

## Authentication Architecture (FastAPI Users)

### Overview
Authentication uses FastAPI Users with JWT tokens. Authentication is **mandatory** - there is no bypass mode.

### Backend Auth Module
```
codeframe/auth/
├── __init__.py          # Module exports
├── dependencies.py      # FastAPI dependencies (get_current_user, etc.)
├── manager.py           # UserManager class
├── models.py            # User model
├── router.py            # Auth routes (/auth/login, /auth/register, etc.)
└── schemas.py           # Pydantic schemas
```

### Frontend Auth Flow
```typescript
// Login stores token in localStorage
localStorage.setItem('auth_token', response.access_token);

// API calls include token via interceptor (lib/api.ts)
config.headers.Authorization = `Bearer ${token}`;

// WebSocket includes token as query parameter
new WebSocket(`${WS_URL}?token=${token}`);
```

### Key Files
- **Backend**: `codeframe/auth/dependencies.py` - `get_current_user()` dependency
- **Frontend**: `web-ui/src/lib/api-client.ts` - `authFetch()` with auto-auth
- **WebSocket**: `web-ui/src/lib/websocket.ts` - Token included in connection URL
- **Context**: `web-ui/src/contexts/AuthContext.tsx` - React auth context

### E2E Testing with Auth
Tests use `loginUser()` helper from `tests/e2e/test-utils.ts`:
```typescript
await loginUser(page);  // Logs in test user, stores token
```

## Frontend State Management Architecture (Phase 5.2)

### Context + Reducer Pattern
The Dashboard uses React Context with useReducer for centralized state management:

- **AgentStateContext** (`web-ui/src/contexts/AgentStateContext.ts`): Global state container
- **agentReducer** (`web-ui/src/reducers/agentReducer.ts`): Pure reducer with 13 action types
- **AgentStateProvider** (`web-ui/src/components/AgentStateProvider.tsx`): Context provider with WebSocket integration
- **useAgentState** (`web-ui/src/hooks/useAgentState.ts`): Custom hook for consuming state

### Key Features
- **Multi-Agent Support**: Handles up to 10 concurrent agents with independent state tracking
- **Real-Time Updates**: WebSocket integration with 9 event types (agent_created, task_assigned, etc.)
- **Automatic Reconnection**: Exponential backoff (1s → 30s) with full state resync
- **Timestamp Conflict Resolution**: Last-write-wins using backend timestamps
- **Performance Optimizations**: React.memo on all Dashboard sub-components, useMemo for derived state
- **Error Boundaries**: ErrorBoundary component wraps AgentStateProvider for graceful error handling

### File Locations
```
web-ui/src/
├── contexts/AgentStateContext.ts
├── components/
│   ├── AgentStateProvider.tsx
│   └── ErrorBoundary.tsx
├── reducers/agentReducer.ts
├── hooks/useAgentState.ts
├── lib/
│   ├── websocketMessageMapper.ts
│   ├── agentStateSync.ts
│   └── validation.ts
└── types/agentState.ts
```

### Testing
- 90 unit & integration tests covering reducer, WebSocket mapping, state sync, and Dashboard integration
- Test files located in `web-ui/__tests__/`

## UI Template Configuration

### shadcn/ui Nova Template

The web-ui uses shadcn/ui with the Nova template for consistent styling:

**Configuration:**
- **Base**: Radix UI primitives
- **Style**: Nova (compact spacing)
- **Base Color**: Gray
- **Theme**: Gray palette
- **Icon Library**: Hugeicons (@hugeicons/react)
- **Font**: Nunito Sans
- **Menu Accent**: Subtle
- **Menu Color**: Default
- **Radius**: Default

**Adding New Components:**
```bash
cd web-ui
npx shadcn@latest add <component-name>
```

Components are automatically styled with Nova theme.

**Color Palette:**
- Background: `bg-background`
- Card: `bg-card`
- Primary: `bg-primary`
- Secondary: `bg-secondary`
- Muted: `bg-muted`
- Accent: `bg-accent`
- Destructive: `bg-destructive`

**Typography:**
- Foreground: `text-foreground`
- Muted: `text-muted-foreground`
- Primary: `text-primary-foreground`

**Verification:**
Check `web-ui/components.json` for template configuration.

### Component Styling Guidelines

**DO:**
- Use shadcn UI components from `@/components/ui/`
- Use Nova color palette variables (`bg-card`, `text-foreground`, etc.)
- Use Hugeicons for all icons
- Follow Nova's compact spacing conventions
- Use `cn()` utility for conditional classes

**DON'T:**
- Use hardcoded color values (e.g., `bg-blue-500`)
- Mix lucide-react with Hugeicons
- Create custom CSS classes (use Tailwind utilities)
- Override Nova theme variables without documentation

**Example:**
```typescript
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Download01Icon } from '@hugeicons/react'

<Card className="bg-card border-border">
  <Button variant="secondary">
    <Download01Icon className="mr-2 h-4 w-4" />
    Export
  </Button>
</Card>
```

## Environment Variables

### Critical: Next.js Build-Time Variables
`NEXT_PUBLIC_*` variables are baked into the JavaScript bundle at **build time**, not runtime.

**Correct deployment pattern:**
```bash
# Set vars BEFORE build
export NEXT_PUBLIC_API_URL="https://api.example.com"
export NEXT_PUBLIC_WS_URL="wss://api.example.com/ws"
npm run build  # Variables are now embedded in bundle
npm start
```

**Common mistake:**
```bash
npm run build  # Variables NOT set - uses defaults
NEXT_PUBLIC_API_URL="https://api.example.com" npm start  # Too late!
```

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `NEXT_PUBLIC_API_URL` | Backend API URL | `http://localhost:8080` |
| `NEXT_PUBLIC_WS_URL` | WebSocket URL | `ws://localhost:8080/ws` |
| `ANTHROPIC_API_KEY` | Claude API key | `sk-ant-...` |

### Frontend API Pattern
All frontend API files must use the standard pattern:
```typescript
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';
```

**Never use:**
- `window.VITE_API_URL` (Vite pattern, not Next.js)
- Hardcoded production URLs
- Different fallback ports

## Known Issues & Gotchas

### WebSocket Authentication
WebSocket connections require auth token as query parameter:
```typescript
// ✅ Correct
new WebSocket(`wss://api.example.com/ws?token=${authToken}`);

// ❌ Wrong - will be rejected with code 1008
new WebSocket('wss://api.example.com/ws');
```

### E2E Test Architecture Policy

**CRITICAL: Never use `test.skip()` inside test logic.**

Using `test.skip()` within test execution masks bugs. If UI doesn't show up due to a bug, the test silently skips instead of failing.

**Correct patterns:**
```typescript
// ✅ Skip at describe level for environmental conditions
test.describe('Feature requiring API key', () => {
  test.skip(!process.env.ANTHROPIC_API_KEY, 'Requires ANTHROPIC_API_KEY');

  test('does something with API', async () => {
    // Test runs OR entire suite is skipped - never silently passes
  });
});

// ✅ Assert UI elements exist - FAIL if missing
test('should show approve button', async ({ page }) => {
  const button = page.getByRole('button', { name: /approve/i });
  await expect(button).toBeVisible();  // FAILS if not visible
  await button.click();
});

// ✅ Use separate test projects for different states
const PROJECT_ID = TEST_PROJECT_IDS.PLANNING;  // Seeded in planning phase
```

**Anti-patterns to avoid:**
```typescript
// ❌ NEVER: Skip inside test logic
test('approves tasks', async ({ page }) => {
  const button = page.getByRole('button', { name: /approve/i });
  if (!(await button.isVisible())) {
    test.skip(true, 'Button not visible');  // MASKS BUGS
    return;
  }
  // ...
});

// ❌ NEVER: Silent pass on missing elements
if (await element.isVisible()) {
  // do assertions
}
// Test passes even if element never shows up!
```

**Test data guarantees:**
- `TEST_PROJECT_IDS.PLANNING` is seeded in planning phase with tasks
- `TEST_PROJECT_IDS.ACTIVE` is seeded in active phase with agents
- If test data doesn't match expectations, that's a bug in `seed-test-data.py`

### E2E Test Limitations (Issue #172)
Current E2E tests have coverage gaps:
- Tests verify DOM exists, not API success
- WebSocket tests accept 0 messages as success
- No console error monitoring

See GitHub issue #172 for planned improvements.

<!-- MANUAL ADDITIONS END -->
