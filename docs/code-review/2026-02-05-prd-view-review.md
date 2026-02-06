# Code Review Report: PRD View - Document Creation & Discovery

**Date:** 2026-02-05
**Reviewer:** Code Review Agent
**Component:** PRD View (PR #337, Issue #330)
**Files Reviewed:** 34 files (20 source, 8 test, 1 mock, 1 docs, 4 config)
**Ready for Production:** Yes, with 2 major issues recommended for near-term fix

## Executive Summary

This PR implements the full PRD View for Phase 3 UI — a well-structured, component-driven implementation across 9 incremental commits. The code follows established project patterns (Shadcn/UI Nova template, Hugeicons, SWR, axios namespace pattern) and includes 64 new tests. Two major reliability issues were found (missing error handling in page.tsx handlers and a misused React hook in DiscoveryPanel), plus a few minor improvements. No critical security vulnerabilities.

**Critical Issues:** 0
**Major Issues:** 2
**Minor Issues:** 4
**Positive Findings:** 7

---

## Review Context

**Code Type:** Frontend (Next.js React components, hooks, API client)
**Risk Level:** Medium (user input handling, file upload, SSE connections, AI chat rendering)
**Business Constraints:** Phase 3 UI rebuild — first user-facing view beyond workspace

### Review Focus Areas

- ✅ A03 - Injection/XSS — User markdown rendered via react-markdown, file upload content
- ✅ Reliability — Error handling in async handlers, resource cleanup in SSE hooks
- ✅ Resource Management — EventSource lifecycle, FileReader cleanup, SWR cache management
- ✅ A06 - Vulnerable Components — Dependency audit
- ❌ OWASP LLM Top 10 — Skipped (frontend doesn't interact with LLM directly)
- ❌ Zero Trust / Auth — Skipped (auth is backend concern; API client already has `withCredentials: true`)
- ❌ Performance — Skipped (not performance-critical UI code)

---

## Priority 1 Issues - Critical ⛔

None found.

---

## Priority 2 Issues - Major ⚠️

### 1. Missing error handling in `handleSavePrd` and `handleGenerateTasks`

**Location:** `web-ui/src/app/prd/page.tsx:89-103` and `web-ui/src/app/prd/page.tsx:118-127`
**Severity:** Major
**Category:** Reliability

**Problem:**
Both `handleSavePrd` and `handleGenerateTasks` use `try...finally` without a `catch` block. If the API call fails, the error propagates as an unhandled rejection. Unlike `DiscoveryPanel` and `UploadPRDModal` (which properly catch and display errors), these handlers silently fail — the user sees the spinner stop but gets no feedback about what went wrong.

**Current Code:**
```typescript
const handleSavePrd = async (content: string, changeSummary: string) => {
  if (!prd || !workspacePath) return;
  setIsSaving(true);
  try {
    const updated = await prdApi.createVersion(...);
    mutatePrd(updated, false);
  } finally {
    setIsSaving(false);
  }
};
```

**Recommended Fix:**
```typescript
const handleSavePrd = async (content: string, changeSummary: string) => {
  if (!prd || !workspacePath) return;
  setIsSaving(true);
  try {
    const updated = await prdApi.createVersion(...);
    mutatePrd(updated, false);
  } catch (err) {
    const apiError = err as ApiError;
    console.error('[PRD] Save failed:', apiError.detail);
    // TODO: Show error toast/banner to user
  } finally {
    setIsSaving(false);
  }
};
```

**Why This Fix Works:**
Prevents unhandled promise rejections and gives the user feedback. A toast/notification system would be the ideal UX, but at minimum logging prevents silent failures.

---

### 2. Misuse of `useState` as initializer in DiscoveryPanel

**Location:** `web-ui/src/components/prd/DiscoveryPanel.tsx:68-70`
**Severity:** Major
**Category:** Reliability / Correctness

**Problem:**
`useState` is being used with a callback to auto-start the discovery session on mount. This is an unconventional pattern — `useState`'s initializer runs during the first render (synchronously), but here it triggers an async side effect (`startSession()`). This works coincidentally because React state initializers run once, but:
1. It violates React's rules — side effects should use `useEffect`
2. The async call fires during render, not after mount
3. React StrictMode in development will call it twice

**Current Code:**
```typescript
useState(() => {
  if (!sessionId) startSession();
});
```

**Recommended Fix:**
```typescript
useEffect(() => {
  if (!sessionId) startSession();
  // eslint-disable-next-line react-hooks/exhaustive-deps
}, []);
```

**Why This Fix Works:**
`useEffect` with `[]` runs after the component mounts, which is the correct lifecycle for firing API calls. The eslint-disable is needed because `startSession` and `sessionId` are intentionally excluded (we only want to run on mount).

---

## Priority 3 Issues - Minor 📝

### 1. `sessionId` interpolated directly into URL path

**Location:** `web-ui/src/lib/api.ts:258`, `270`
**Severity:** Minor
**Category:** A03 - Injection (Defense in depth)

**Recommendation:**
`sessionId` is interpolated into the URL path via template literal: `` `/api/v2/discovery/${sessionId}/answer` ``. While `sessionId` comes from the server (not user input), encoding it would add defense-in-depth against future misuse.

**Suggested Approach:**
```typescript
`/api/v2/discovery/${encodeURIComponent(sessionId)}/answer`
```

This is a nitpick — the backend validates the session ID format, and the value originates from the server. No immediate risk.

---

### 2. No file size limit on upload

**Location:** `web-ui/src/components/prd/UploadPRDModal.tsx:45-67`
**Severity:** Minor
**Category:** Reliability

**Recommendation:**
The file upload handler reads the entire file into memory via `FileReader.readAsText()` without checking file size. A user could accidentally select a very large file (e.g., a binary misnamed `.md`), causing browser memory issues.

**Suggested Approach:**
Add a size check before reading:
```typescript
const MAX_FILE_SIZE = 5 * 1024 * 1024; // 5 MB
if (file.size > MAX_FILE_SIZE) {
  setError('File too large (max 5 MB)');
  return;
}
```

---

### 3. `genResp` variable unused in `handleGeneratePrd`

**Location:** `web-ui/src/components/prd/DiscoveryPanel.tsx:124`
**Severity:** Minor
**Category:** Code Quality

**Recommendation:**
The response from `discoveryApi.generatePrd()` is assigned to `genResp` but never used — the function immediately fetches the full PRD via `prdApi.getLatest()`. This is correct behavior (the generate endpoint returns a preview, not the full PRD), but the unused variable should be removed for clarity.

**Suggested Approach:**
```typescript
await discoveryApi.generatePrd(sessionId, workspacePath);
const fullPrd = await prdApi.getLatest(workspacePath);
```

---

### 4. DiscoveryPanel and PRDView lack test coverage

**Location:** `web-ui/src/components/prd/DiscoveryPanel.tsx`, `PRDView.tsx`
**Severity:** Minor
**Category:** Test Coverage

**Recommendation:**
DiscoveryPanel (0% coverage) and PRDView (0% coverage) are the two orchestrator components that tie everything together. While their child components are well-tested (93-100%), the orchestrators contain the async API flow logic (session start, answer submission, PRD generation) that is most likely to break in production.

**Suggested Approach:**
Add tests that mock `@/lib/api` and SWR, then verify:
- DiscoveryPanel: session auto-start, answer submission flow, error display
- PRDView: loading/empty/content state rendering, discovery toggle

---

## Positive Findings ✨

### Excellent Practices
- **Consistent error pattern:** All API-facing components (`DiscoveryPanel`, `UploadPRDModal`, `DiscoveryInput`) use `try/catch/finally` with typed `ApiError` extraction — follows the project's established `normalizeErrorDetail` pattern.
- **SWR optimistic updates:** `mutatePrd(newPrd, false)` correctly uses `false` for `revalidate` to avoid redundant refetches after mutations.
- **Proper React patterns:** Stable callback refs in `useEventSource` prevent unnecessary effect re-runs. `useCallback` used consistently for handlers passed to children.

### Good Architectural Decisions
- **Incremental commits:** Each of the 9 commits is independently reviewable and represents a testable increment — excellent for bisecting bugs.
- **Component separation:** Clear responsibility split (PRDView = layout, PRDHeader = actions, MarkdownEditor = content, DiscoveryPanel = chat lifecycle). Each component is independently testable.
- **Generic + specific hook pattern:** `useEventSource` (generic SSE) wrapping into `useTaskStream` (typed for task events) is a clean, reusable pattern.

### Security Wins
- **react-markdown 10.1.0:** Uses `micromark` parser which does not support raw HTML by default — safe against XSS in markdown content without needing `rehype-raw` or `rehype-sanitize`.
- **`accept` attribute on file input:** Limits file picker to `.md,.markdown,.txt` — client-side defense against wrong file types.
- **API client `withCredentials: true`:** Already configured in the existing axios instance — cookies sent with cross-origin requests, matching backend auth pattern.
- **Zero npm audit vulnerabilities:** `npm audit --production` shows 0 vulnerabilities.

---

## Team Collaboration Needed

### Handoffs to Other Agents

**Architecture Agent:**
- The `AppSidebar` reads workspace state from `localStorage` independently of the workspace page's own state management. If the workspace is deselected on the home page, the sidebar relies on a `storage` event listener to update. Consider a shared React context for workspace state to ensure consistency.

**UX Designer Agent:**
- Error feedback for `handleSavePrd` and `handleGenerateTasks` failures currently has no visual indicator — user sees spinner stop but no message. A toast/notification system should be prioritized.
- Disabled nav items in the sidebar show as dimmed text with no tooltip on mobile (icon-only mode). Consider adding `title` tooltips on the icon-only view.

---

## Testing Recommendations

### Unit Tests Needed
- [x] PRDHeader (10 tests) ✅
- [x] AssociatedTasksSummary (4 tests) ✅
- [x] MarkdownEditor (8 tests) ✅
- [x] DiscoveryTranscript (6 tests) ✅
- [x] DiscoveryInput (9 tests) ✅
- [x] AppSidebar (7 tests) ✅
- [x] useEventSource (9 tests) ✅
- [x] useTaskStream (9 tests) ✅
- [ ] DiscoveryPanel (mock API, test session lifecycle)
- [ ] PRDView (test state-driven rendering)
- [ ] UploadPRDModal (mock prdApi.create, test submit flow)

### Integration Tests
- [ ] Full discovery flow: mount → auto-start → answer questions → generate PRD
- [ ] Upload PRD via paste → verify editor populated
- [ ] Task generation → verify AssociatedTasksSummary updates

---

## Future Considerations

### Patterns for Project Evolution
- **Toast/notification system:** Multiple components need user-facing error feedback. Consider adding a lightweight toast (e.g., Sonner or Shadcn Toast) before building more views.
- **Workspace context:** As more pages are added (Tasks, Execution, Blockers, Review), workspace state should move from localStorage + per-page hooks to a shared React context.

### Technical Debt Items
- `useState` misuse in DiscoveryPanel (issue #2 above) — should be fixed before more components copy this pattern
- Unused `genResp` variable (issue #3 above)

---

## Compliance & Best Practices

### Security Standards Met
- ✅ No raw HTML rendering in markdown (react-markdown default config)
- ✅ File upload restricted by `accept` attribute
- ✅ API client uses `withCredentials` for cookie-based auth
- ✅ No secrets or credentials in frontend code
- ✅ Zero npm audit vulnerabilities
- ✅ User input sent to API via POST body (not URL path), except workspace_path which is from localStorage

### Enterprise Best Practices
- ✅ TypeScript strict types for all API responses
- ✅ Consistent error handling pattern across components
- ✅ 64 tests with 93-100% coverage on tested components
- ⚠️ Two orchestrator components (DiscoveryPanel, PRDView) at 0% coverage

---

## Action Items Summary

### Immediate (Before Merge - Recommended)
1. Add `catch` blocks to `handleSavePrd` and `handleGenerateTasks` in `page.tsx`
2. Replace `useState()` with `useEffect()` for auto-start in `DiscoveryPanel.tsx`

### Short-term (Next Sprint)
1. Add toast/notification system for error feedback
2. Add tests for DiscoveryPanel and PRDView orchestrator components
3. Add file size validation to UploadPRDModal

### Long-term (Backlog)
1. Workspace state context (replace localStorage reads per-component)
2. `encodeURIComponent` for path-interpolated IDs in API client
3. Remove unused `genResp` variable

---

## Conclusion

This is a well-executed PR that delivers a complete PRD View with strong component architecture, comprehensive tests for leaf components, and proper security defaults. The two major issues (missing error handling and misused `useState`) are straightforward fixes that don't require architectural changes. The codebase follows established patterns consistently across all 20 source files.

**Recommendation:** Fix the 2 major issues, then merge. Short-term items can be addressed in follow-up.

---

## Appendix

### Tools Used for Review
- Manual code review of all 34 changed files
- `npm audit --production` — 0 vulnerabilities
- `npx tsc --noEmit` — 0 new type errors
- `npx jest` — 152/152 tests passing
- react-markdown version check (v10.1.0 — safe defaults)

### References
- OWASP Top 10 Web Application Security (A03, A06, A07)
- React Rules of Hooks documentation
- react-markdown security model (micromark parser, no raw HTML by default)

### Metrics
- **Lines of Code Reviewed:** ~2,400 (source), ~880 (tests)
- **Components Reviewed:** 10 new components, 2 hooks, 1 API client extension
- **Security Patterns Checked:** 6 (XSS, injection, file upload, auth headers, dependency audit, resource cleanup)
