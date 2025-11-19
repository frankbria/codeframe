# API Contracts: Server Start Command

**Feature**: 010-server-start-command

---

## No API Contracts

This feature **does not add or modify any API endpoints**.

The `codeframe serve` command is a **CLI-only feature** that starts the existing FastAPI server. It does not introduce new HTTP routes, WebSocket handlers, or GraphQL resolvers.

---

## Why No Contracts?

The serve command's responsibility is **server lifecycle management**:
- Start uvicorn subprocess
- Check port availability
- Open browser
- Handle graceful shutdown

It **does not** expose any APIs to external clients.

---

## Existing APIs

The server that is *started* by this command already has APIs documented elsewhere:
- `/api/projects` - Project management endpoints
- `/api/agents` - Agent management endpoints
- `/api/blockers` - Blocker management endpoints
- `/ws` - WebSocket for real-time updates

See `/home/frankbria/projects/codeframe/codeframe/ui/server.py` for full API documentation.

---

## Future Considerations

If we later add features like:
- Server management API (start/stop/status via HTTP)
- Multi-instance coordination
- Remote server control

...then we would document those contracts here. For now, this directory remains empty by design.
