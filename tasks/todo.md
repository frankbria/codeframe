# Issue #563 — GitHub Issues import: repository connection (PAT auth)

**Phase 5.5** · branch `feat/563-github-integration-connect` (to be created)

## Goal
Let users connect a GitHub repo to their CodeFRAME workspace via a Personal Access
Token so issues can later be imported. Backend connect/disconnect/status endpoints +
an "Integrations" tab on the existing Settings page.

## Why the Traycer plan was rewritten
The Traycer plan (commit 3f14270) targets a `codeframe/persistence/` module with a new
`github_integrations` table + repository + schema migration. That module was **renamed
and slimmed to `codeframe/platform_store/` (control-plane only) in #599**, and the
actual #555 pattern stores secrets in the **machine-wide `CredentialManager`** (keyring /
Fernet file) with non-secret config in **per-workspace `.codeframe/*.json`** — *not* the
control-plane DB. So: no new DB table, no repository, no migration. We follow the real
`settings_v2` + `notifications_config` conventions instead.

## Design decisions
- **PAT storage**: machine-wide `CredentialManager.set_credential(CredentialProvider.GIT_GITHUB, pat)`.
  Already the slot the API Keys tab (#555) uses. Encrypted at rest, env-var precedence,
  never returned in plaintext. Disconnect deletes it.
- **Repo metadata** (`repo`, `owner_login`, `owner_avatar_url`, `connected_at`):
  per-workspace `.codeframe/github_integration.json`, headless module mirroring
  `core/notifications_config.py`.
- **Validation**: headless `core/github_connect_service.py` using `httpx.AsyncClient`
  (same as `git/github_integration.py`). Validates `owner/repo`, calls GitHub API,
  verifies issues-read access, raises typed errors.
- **Known limitation**: the GitHub PAT is machine-wide (shared with the API Keys tab's
  GitHub slot); disconnecting clears it everywhere. Repo *selection* is per-workspace.
  (v1 — matches #555 "same pattern as API key storage" intent.)

## Steps

### Backend
1. **`codeframe/core/github_connect_service.py`** (new, headless)
   - Typed errors: `GitHubConnectError` (base), `InvalidTokenError`, `RepoNotFoundError`,
     `InsufficientScopeError`.
   - `parse_repo(repo) -> (owner, name)` — raises `ValueError` on bad `owner/repo` format.
   - `async validate_connection(pat, repo) -> {owner_login, owner_avatar_url, repo_full_name}`:
     `GET /repos/{owner}/{repo}` (401→InvalidToken, 404→RepoNotFound),
     then `GET /repos/{owner}/{repo}/issues?per_page=1` (403→InsufficientScope; 200/410→ok).
   - Tests: `tests/core/test_github_connect_service.py` (mock httpx transport).

2. **`codeframe/core/github_integration_config.py`** (new, headless)
   - `load_github_integration_config(workspace) -> dict | None`
   - `save_github_integration_config(workspace, cfg)` (atomic write, like notifications_config)
   - `clear_github_integration_config(workspace)`
   - Tests: `tests/core/test_github_integration_config.py`.

3. **`codeframe/ui/routers/github_integrations_v2.py`** (new router)
   - prefix `/api/v2/integrations/github`, tag `integrations`.
   - `get_credential_manager` dependency (local, overridable in tests — mirrors settings_v2).
   - Pydantic: `ConnectRequest{pat, repo}`, `ConnectResponse{connected, repo, owner_login, owner_avatar_url}`,
     `StatusResponse{connected, repo?, owner_login?, owner_avatar_url?}`.
   - `POST /connect` (`@rate_limit_ai`): validate format (400), `validate_connection`
     (401/404/403), store PAT, save repo config, return ConnectResponse. **PAT never echoed.**
   - `DELETE /disconnect` (`@rate_limit_standard`): clear config + delete credential → 204.
   - `GET /status` (`@rate_limit_standard`): connected = repo config present AND credential present.
   - Tests: `tests/ui/test_github_integrations_v2.py` (TestClient, override
     `get_v2_workspace` + `get_credential_manager`, mock `validate_connection`).

4. **`codeframe/ui/server.py`**: import + `include_router(github_integrations_v2.router)`
   + add `{"name": "integrations", ...}` to `OPENAPI_TAGS`.

### Frontend
5. **`web-ui/src/types/index.ts`**: `GitHubIntegrationStatus`, `GitHubConnectRequest`,
   `GitHubConnectResponse`.
6. **`web-ui/src/lib/api.ts`**: `integrationsApi.getStatus/connect/disconnect`
   (all pass `workspace_path`).
7. **`web-ui/src/components/settings/GitHubIntegrationCard.tsx`** (new): useSWR status;
   disconnected = PAT (password) + repo inputs + Connect + mapped error message;
   connected = avatar + repo + Disconnect. Pattern mirrors `NotificationsTab.tsx`.
8. **`web-ui/src/app/settings/page.tsx`**: add "Integrations" `TabsTrigger` + `TabsContent`
   rendering `<GitHubIntegrationCard workspacePath={workspacePath} />`.
9. Sidebar `/settings` link already exists — no change.
   - Tests: `web-ui/src/__tests__/components/settings/GitHubIntegrationCard.test.tsx`.

## Acceptance criteria
- [ ] Can connect with a valid PAT and repo
- [ ] Invalid PAT or missing scope shows a clear error
- [ ] Disconnect clears the stored credential
- [ ] PAT never returned in plaintext
- [ ] `npm test` and `uv run pytest` pass

## Test strategy
- AC1 → service `validate_connection` success + router POST 200 + frontend connect→connected.
- AC2 → service raises typed errors; router maps to 401/403; frontend renders friendly text.
- AC3 → router DELETE clears config + credential; status→disconnected.
- AC4 → assert no response body (connect/status) contains the PAT string.
- AC5 → `uv run pytest` (focused), `cd web-ui && npm test && npm run build`.
