# End-to-End Testing (E2E)

## Overview

CodeFRAME has comprehensive E2E test coverage with 47 tests (10 backend Pytest, 37 frontend Playwright) validating the complete autonomous workflow from discovery through completion.

## Running E2E Tests

### Frontend Tests (Playwright)

```bash
cd tests/e2e
npx playwright test  # Backend auto-starts on port 8080
```

**What happens automatically**:
1. Backend server starts with health check on port 8080
2. Frontend dev server starts on port 3000
3. Database seeding runs (via global-setup.ts)
4. Tests execute across browsers (Chromium, Firefox, WebKit)
5. Servers shut down after completion

### Backend Tests (Pytest)

```bash
uv run pytest tests/e2e/test_*.py -v -m "e2e"
```

## Key Configuration

### Playwright Auto-Start

`tests/e2e/playwright.config.ts`:
```typescript
webServer: [
  {
    command: 'cd ../.. && uv run uvicorn codeframe.ui.server:app --port 8080',
    url: 'http://localhost:8080/health',
    timeout: 120000,
    reuseExistingServer: !process.env.CI
  },
  // Frontend server config...
]
```

### Health Endpoint

`codeframe/ui/server.py`:
```python
@app.get("/health")
async def health_check():
    return {"status": "ok"}
```

## Troubleshooting

### Port 8080 already in use

```bash
# Check what's using port 8080
lsof -i:8080

# If it's a CodeFrame server you want to stop:
lsof -ti:8080 -c python | xargs kill

# Only use kill -9 as last resort (kills ALL processes on port)
# lsof -ti:8080 | xargs kill -9  # ⚠️  Use with caution

# Alternative: Let Playwright reuse the existing server
# (enabled by default via reuseExistingServer: true in playwright.config.ts)
```

### Backend health check timeout

```bash
# Test backend manually (from project root)
uv run uvicorn codeframe.ui.server:app --port 8080
curl http://localhost:8080/health  # Should return {"status": "ok"}
```

### Database seeding errors

```bash
# Remove test databases if needed (rarely necessary)
rm -f tests/e2e/fixtures/*/test_state.db
rm -f .codeframe/test_state.db

# Note: Database seeding uses INSERT OR REPLACE to avoid conflicts
# UNIQUE constraint warnings should NOT occur (if they do, report as bug)
```

### Frontend server timeout

```bash
cd web-ui
npm install
npm run dev  # Should start on port 3000
```

## Best Practices

1. **Use auto-start**: Rely on Playwright's `webServer` config (don't manually start backend)
2. **Check health endpoint**: Ensure `/health` responds quickly (<100ms)
3. **Clean databases**: Remove test databases between test runs if needed
4. **Ignore UNIQUE warnings**: Database seeding warnings are expected and harmless
5. **CI mode**: In CI (`CI=true`), servers are NOT auto-started (CI starts them separately)
6. **Port conflicts**: Kill processes on 8080/3000 before running tests locally

## Test Coverage

E2E tests validate:
- Full workflow: Discovery → Planning → Execution → Completion
- Quality gates blocking on failures
- Checkpoint creation and restoration
- Review agent security detection
- Cost tracking accuracy
- Real-time dashboard updates
- Multi-agent coordination

See [tests/e2e/README.md](../tests/e2e/README.md) for comprehensive testing documentation.
