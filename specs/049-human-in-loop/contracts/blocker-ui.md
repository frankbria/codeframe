# Blocker UI Component Contract

## Components

### BlockerPanel

Displays list of active blockers in dashboard sidebar.

**Props**:
```typescript
interface BlockerPanelProps {
  projectId: number;
  onBlockerClick: (blockerId: number) => void;
}
```

**Behavior**:
- Fetches blockers via `GET /api/projects/:projectId/blockers?status=pending`
- Updates every 10s (polling fallback) + WebSocket events
- Shows blocker count badge: "3 Blockers"
- Each blocker shows:
  - Question preview (first 50 chars + "...")
  - Agent name
  - Time waiting (human-readable: "2m ago", "1h ago")
  - SYNC/ASYNC badge (red/yellow)
- Click blocker → calls `onBlockerClick(blocker_id)`

**State**:
```typescript
{
  blockers: Blocker[];
  loading: boolean;
  error: string | null;
}
```

---

### BlockerModal

Modal for resolving a blocker.

**Props**:
```typescript
interface BlockerModalProps {
  blocker: Blocker | null;  // null = closed
  onClose: () => void;
  onResolve: (blockerId: number, answer: string) => Promise<void>;
}
```

**Behavior**:
- Opens when `blocker` prop is non-null
- Shows:
  - Full question text
  - Task context (task title, description)
  - Agent name
  - Time waiting
  - SYNC/ASYNC indicator
  - Answer textarea (5000 char limit)
  - Submit button
  - Cancel button
- On submit:
  - Validates answer (non-empty, ≤5000 chars)
  - Calls `onResolve(blocker.id, answer)`
  - Shows loading spinner
  - On success: closes modal, shows toast "Blocker resolved!"
  - On error (409): shows "Already resolved by another user"
  - On error (422): shows validation error
- On cancel: calls `onClose()`

**State**:
```typescript
{
  answer: string;
  submitting: boolean;
  error: string | null;
}
```

---

### BlockerBadge

Visual indicator for blocker type.

**Props**:
```typescript
interface BlockerBadgeProps {
  type: 'SYNC' | 'ASYNC';
  size?: 'sm' | 'md' | 'lg';
}
```

**Rendering**:
- SYNC: Red background, "CRITICAL" text, ⚠️ icon
- ASYNC: Yellow background, "INFO" text, ℹ️ icon
- Sizes: sm=16px, md=24px, lg=32px

---

## User Interactions

### Workflow: Resolve a Blocker

1. User sees blocker in BlockerPanel
2. Clicks blocker → BlockerModal opens
3. Reads question and context
4. Types answer in textarea
5. Clicks "Submit"
6. Modal shows loading spinner
7. API call succeeds
8. Modal closes, toast shows "Blocker resolved!"
9. WebSocket broadcast updates all dashboards
10. Blocker disappears from panel

### Edge Cases

- **Double resolution**: Second user sees "Already resolved" message, modal closes
- **Empty answer**: Submit button disabled, validation error shown
- **Long answer**: Character counter shows "4500/5000", prevents >5000
- **Network error**: Retry button appears, allows resubmission
