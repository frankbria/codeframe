# codeframe Development Guidelines

Auto-generated from all feature plans. Last updated: 2025-12-23

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

<!-- MANUAL ADDITIONS END -->
