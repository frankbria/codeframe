# Account Table Migration: BetterAuth Integration

**Date**: 2026-01-02
**Status**: Schema Migration Complete, BetterAuth Integration In Progress
**Branch**: `e2e-user-journey-tests`

## Overview

This migration transforms CodeFRAME's authentication schema from a simple password-in-users-table model to BetterAuth's OAuth-ready architecture with passwords stored in a separate accounts table.

## Motivation

- **OAuth Support**: BetterAuth's architecture separates user identity (users table) from authentication credentials (accounts table), enabling future OAuth provider integration
- **Industry Standard**: Matches authentication best practices used by major platforms
- **Scalability**: Supports multiple authentication methods per user (email/password + OAuth)

## Schema Changes

### Before Migration

```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,  -- ❌ Removed
    name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE sessions (
    token TEXT PRIMARY KEY,  -- ❌ Changed to id
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### After Migration

```sql
-- Users table: Core user information (no password)
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    name TEXT,
    email_verified INTEGER DEFAULT 0,  -- ✅ Added
    image TEXT,                        -- ✅ Added
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Accounts table: Authentication credentials (NEW)
CREATE TABLE accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    account_id TEXT NOT NULL,           -- Email or OAuth provider ID
    provider_id TEXT NOT NULL,          -- 'credential' for email/password, 'google'/'github' for OAuth
    password TEXT,                      -- bcrypt hash for email/password auth
    access_token TEXT,                  -- OAuth access token
    refresh_token TEXT,                 -- OAuth refresh token
    expires_at TIMESTAMP,               -- OAuth token expiry
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, provider_id)
);

-- Sessions table: Active user sessions
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,                -- ✅ Added as primary key
    token TEXT UNIQUE NOT NULL,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TIMESTAMP NOT NULL,
    ip_address TEXT,                    -- ✅ Added
    user_agent TEXT,                    -- ✅ Added
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Migration Strategy

### 1. Backend Schema (Python)

**File**: `codeframe/persistence/schema_manager.py`

- Updated `_create_auth_tables()` to create BetterAuth-compatible tables
- Updated `_ensure_default_admin_user()` to create account entries
- Changes are backward-compatible: uses `CREATE TABLE IF NOT EXISTS`

### 2. Frontend Schema (TypeScript)

**File**: `web-ui/src/lib/db-schema.ts`

- Added Drizzle ORM schema for users, accounts, and sessions tables
- Schema matches backend exactly (snake_case column names)
- Used by BetterAuth's `drizzleAdapter`

**File**: `web-ui/src/lib/auth.ts`

- Configured BetterAuth with Drizzle adapter
- Uses `usePlural: true` for table naming (users/sessions vs user/session)
- Connects to same SQLite database as backend

### 3. Migration Script

**File**: `codeframe/persistence/migrations/migrate_to_accounts_table.py`

**Usage**:
```bash
python migrate_to_accounts_table.py /path/to/database.db
```

**Features**:
- **Idempotent**: Safe to run multiple times (checks for `password_hash` column)
- **Data Preservation**: Migrates existing passwords to accounts table
- **SQLite Workaround**: Recreates users table to drop password_hash column
- **Session Upgrade**: Adds id primary key to sessions table

**Process**:
1. Backup existing user data
2. Create accounts table
3. Migrate password_hash → accounts table (provider_id='credential')
4. Recreate users table without password_hash column
5. Update sessions table structure

### 4. Test Data Seeding

**File**: `tests/e2e/seed-test-data.py`

- Updated to create users without password_hash
- Creates corresponding account entries for test users
- Test user: email=`test@example.com`, password=`testpassword123`

## Files Modified

### Backend
- `codeframe/persistence/schema_manager.py` - Schema definitions
- `codeframe/persistence/migrations/migrate_to_accounts_table.py` - Migration script (NEW)

### Frontend
- `web-ui/src/lib/db-schema.ts` - Drizzle schema (updated)
- `web-ui/src/lib/auth.ts` - BetterAuth config (already using Drizzle adapter)

### Tests
- `tests/e2e/seed-test-data.py` - Test data seeding (updated)

### Backend Auth (No Changes Needed)
- `codeframe/ui/auth.py` - ✅ No changes required
  - Only validates session tokens, doesn't verify passwords
  - BetterAuth handles all password authentication on frontend

## Current Status

### ✅ Completed

1. **Backend Schema Migration**: All tables updated to BetterAuth-compatible structure
2. **Frontend Schema Definition**: Drizzle schema matches backend exactly
3. **Migration Script**: Idempotent script for upgrading existing databases
4. **Test Data Seeding**: E2E tests create BetterAuth-compatible data
5. **Database Migration**: Main database (`../.codeframe/state.db`) migrated successfully

### 🔧 In Progress

**BetterAuth Login Integration**: Schema fixed, but login still timing out

**Latest Update (2026-01-02 16:00)**:
- ✅ Fixed critical schema mismatch: accounts.id changed from INTEGER to TEXT
- ✅ Added BetterAuth-required OAuth fields (id_token, access_token_expires_at, etc.)
- ✅ Database schema now 100% matches BetterAuth requirements
- ✘ Login timeouts persist despite schema fixes

**Current Symptoms**:
- ✅ Login page renders correctly
- ✅ Form validation works (empty fields, invalid email format)
- ✅ Invalid email (user doesn't exist) → Fast error response
- ✘ Valid email + any password → Timeout after 10-30s
- ✘ Timeout occurs whether password is correct or incorrect

**Analysis**:
The pattern suggests BetterAuth successfully queries the database and finds the user/account, but then hangs during password verification or session creation. Possible causes:

1. **Password Hashing Mismatch**:
   - We're storing bcrypt hashes from Python (bcrypt.hashpw)
   - BetterAuth may use a different bcrypt implementation
   - May need to verify hash format compatibility

2. **Async Database Operations**:
   - BetterAuth might be waiting for a promise that never resolves
   - Drizzle adapter async query handling issue

3. **Session Creation Blocking**:
   - Session table write might be failing
   - BetterAuth retrying session creation indefinitely

**Investigation Needed**:
- [ ] Test BetterAuth sign-up flow (creates new account with BetterAuth's hash)
- [ ] Compare bcrypt hash format: Python vs BetterAuth JavaScript
- [ ] Enable BetterAuth debug logging to see where it hangs
- [ ] Test direct API call to /api/auth/sign-in with curl
- [ ] Check if sessions table writes are succeeding

**Schema Fixes Applied**:
```sql
-- OLD (broke BetterAuth)
CREATE TABLE accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- ❌ Wrong type
    ...
);

-- NEW (BetterAuth compatible)
CREATE TABLE accounts (
    id TEXT PRIMARY KEY,                    -- ✅ Correct
    ...
    id_token TEXT,                          -- ✅ Added
    access_token_expires_at TIMESTAMP,      -- ✅ Added
    refresh_token_expires_at TIMESTAMP,     -- ✅ Added
    scope TEXT,                              -- ✅ Added
);
```

Sources:
- [BetterAuth Drizzle Adapter Schema](https://www.better-auth.com/docs/adapters/drizzle)
- [BetterAuth User & Accounts Docs](https://www.better-auth.com/docs/concepts/users-accounts)

## Rollback Plan

If needed, migration can be reversed:

1. **Database**: Restore from backup (migration script doesn't delete old data)
2. **Code**: Revert commits on `e2e-user-journey-tests` branch
3. **Schema**: Old schema is preserved in git history

## Next Steps

1. Debug BetterAuth login timeout issue
2. Verify BetterAuth configuration matches schema
3. Run E2E tests to confirm login flow works
4. Document any additional BetterAuth configuration needed
5. Create pull request with migration changes

## References

- [BetterAuth Documentation](https://better-auth.com/docs)
- [BetterAuth Drizzle Adapter](https://better-auth.com/docs/adapters/drizzle)
- [BetterAuth Email/Password Provider](https://better-auth.com/docs/providers/email-password)
- Issue #158: Unified Auth System Implementation
