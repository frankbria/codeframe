# Account Table Migration: BetterAuth Integration

> **STATUS: SUPERSEDED**
>
> This migration was **abandoned** on 2026-01-02 in favor of **FastAPI Users** authentication.
> The BetterAuth integration described here was never completed due to persistent timeout issues.
>
> **Current auth system**: FastAPI Users with JWT tokens
> **See**: [authentication.md](./authentication.md) for current documentation

---

**Date**: 2026-01-02
**Final Status**: Superseded by FastAPI Users migration
**Original Branch**: `e2e-user-journey-tests`

## Historical Context

This document preserves the history of an attempted migration from simple password-in-users-table authentication to BetterAuth's OAuth-ready architecture. The migration was abandoned after encountering persistent timeout issues that could not be resolved.

### What Was Attempted

1. **Schema Migration**: Transform users table to separate credentials into accounts table
2. **BetterAuth Integration**: Use BetterAuth v1.4.7 for frontend authentication
3. **Drizzle ORM**: Frontend schema definition for BetterAuth adapter

### Why It Was Abandoned

Despite extensive debugging:

1. **Timeout Issues**: Login requests would hang indefinitely with valid credentials
2. **bcrypt Compatibility**: Initially suspected, but confirmed NOT the issue
3. **Schema Mismatches**: Multiple schema fixes applied but timeouts persisted
4. **Time Constraints**: Decision made to use simpler, proven FastAPI Users library

### Resolution

On 2026-01-02, the decision was made to:

1. **Abandon BetterAuth** - Too many unresolved integration issues
2. **Adopt FastAPI Users** - Production-ready, well-documented Python auth library
3. **Use JWT Tokens** - Stateless authentication with 1-hour lifetime
4. **Delete Frontend Auth Files** - Remove `web-ui/src/lib/auth.ts` and `auth-client.ts`

### Files Deleted After Migration

- `web-ui/src/lib/auth.ts` - BetterAuth client configuration
- `web-ui/src/lib/auth-client.ts` - BetterAuth API client
- `web-ui/src/lib/db-schema.ts` - Drizzle schema (BetterAuth specific)

### Current Architecture

The project now uses:

```
codeframe/auth/           # FastAPI Users module
├── dependencies.py       # get_current_user() dependency
├── manager.py            # UserManager, JWT strategy
├── models.py             # SQLAlchemy User model
├── router.py             # Auth routes
└── schemas.py            # Pydantic schemas
```

**Authentication flow**:
1. User registers/logs in via `/auth/register` or `/auth/jwt/login`
2. Backend returns JWT access token
3. Frontend stores token in localStorage
4. All API requests include `Authorization: Bearer <token>`
5. WebSocket connections pass token as query parameter

---

## Original Document (For Historical Reference)

The sections below are preserved for historical context only. They describe work that was never completed.

<details>
<summary>Click to expand original migration plan (NOT IMPLEMENTED)</summary>

### Overview (NOT IMPLEMENTED)

This migration transforms CodeFRAME's authentication schema from a simple password-in-users-table model to BetterAuth's OAuth-ready architecture with passwords stored in a separate accounts table.

### Motivation (Historical)

- **OAuth Support**: BetterAuth's architecture separates user identity (users table) from authentication credentials (accounts table), enabling future OAuth provider integration
- **Industry Standard**: Matches authentication best practices used by major platforms
- **Scalability**: Supports multiple authentication methods per user (email/password + OAuth)

### Schema Changes (NOT APPLIED)

```sql
-- Proposed accounts table (NOT CREATED)
CREATE TABLE accounts (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    account_id TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    password TEXT,
    access_token TEXT,
    refresh_token TEXT,
    ...
);
```

### Debugging Timeline

| Date | Issue | Attempted Fix | Result |
|------|-------|---------------|--------|
| 2026-01-02 AM | Login timeout | Schema alignment | Failed |
| 2026-01-02 PM | bcrypt compatibility | Cross-platform testing | Confirmed NOT issue |
| 2026-01-02 PM | Schema mismatch | accounts.id TEXT fix | Timeout persisted |
| 2026-01-02 EVE | Decision | Abandon BetterAuth | Adopted FastAPI Users |

</details>

---

## Lessons Learned

1. **Evaluate libraries thoroughly** before committing to integration
2. **Time-box debugging** - know when to pivot to alternatives
3. **Document abandoned approaches** to prevent re-attempting failed paths
4. **Prefer server-side auth** in monorepos to avoid client/server coordination complexity

---

**See [authentication.md](./authentication.md) for current authentication documentation.**
