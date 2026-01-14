# Web UI Setup Guide

CodeFRAME includes a real-time web dashboard for monitoring agent activity.

## Architecture

```
┌──────────────────────────────────────────────────┐
│  Web UI (Next.js + TypeScript)                   │
│  http://localhost:3000                           │
│  ├─ Dashboard (real-time updates)                │
│  ├─ Agent status cards                           │
│  ├─ Task progress tracking                       │
│  ├─ Blocker management                           │
│  └─ Chat interface                               │
└────────────┬─────────────────────────────────────┘
             │ REST API + WebSocket
┌────────────▼─────────────────────────────────────┐
│  Status Server (FastAPI)                         │
│  http://localhost:8080                           │
│  ├─ /api/projects - Project management           │
│  ├─ /api/agents - Agent status                   │
│  ├─ /api/tasks - Task operations                 │
│  ├─ /api/blockers - Blocker resolution           │
│  ├─ /api/chat - Lead Agent communication         │
│  └─ /ws - WebSocket real-time updates            │
└────────────┬─────────────────────────────────────┘
             │
┌────────────▼─────────────────────────────────────┐
│  CodeFRAME Core (Python)                         │
│  ├─ Project management                           │
│  ├─ Agent orchestration                          │
│  ├─ SQLite database                              │
│  └─ Context management                           │
└──────────────────────────────────────────────────┘
```

## Quick Start

### 1. Start Status Server (FastAPI)

```bash
# From project root
python -m codeframe.ui.server

# Or with custom host/port
python -m codeframe.ui.server --host 0.0.0.0 --port 8080
```

The API will be available at http://localhost:8080

### 2. Start Web UI (Next.js)

```bash
# Navigate to web-ui directory
cd web-ui

# Install dependencies (first time only)
npm install

# Start development server
npm run dev
```

The dashboard will be available at http://localhost:3000

## Development

### Backend (FastAPI)

**Location**: `codeframe/ui/server.py`

**Features**:
- ✅ RESTful API endpoints
- ✅ WebSocket real-time updates
- ✅ CORS support for local development
- ✅ Connection manager for WebSocket clients
- 🚧 Integration with Project/Database layers

**Extending the API**:
```python
@app.get("/api/custom-endpoint")
async def custom_endpoint():
    return {"data": "value"}
```

### Frontend (Next.js)

**Location**: `web-ui/src/`

**Structure**:
```
web-ui/
├── src/
│   ├── app/              # Next.js App Router
│   │   ├── page.tsx      # Home page
│   │   ├── layout.tsx    # Root layout
│   │   └── globals.css   # Global styles
│   ├── components/       # React components
│   │   └── Dashboard.tsx # Main dashboard
│   ├── lib/              # Utilities
│   │   ├── api.ts        # API client
│   │   └── websocket.ts  # WebSocket client
│   └── types/            # TypeScript types
│       └── index.ts      # Type definitions
├── public/               # Static assets
├── package.json
├── tsconfig.json
└── tailwind.config.ts
```

**Adding Components**:
```tsx
// src/components/MyComponent.tsx
export default function MyComponent() {
  return <div>My Component</div>;
}
```

## API Endpoints

### Projects

- `GET /api/projects` - List all projects
- `GET /api/projects/{id}/status` - Get project status
- `POST /api/projects/{id}/pause` - Pause project
- `POST /api/projects/{id}/resume` - Resume project

### Agents

- `GET /api/projects/{id}/agents` - Get agent status

### Tasks

- `GET /api/projects/{id}/tasks` - List tasks
  - Query params: `status`, `limit`

### Blockers

- `GET /api/projects/{id}/blockers` - Get pending blockers
- `POST /api/projects/{id}/blockers/{blocker_id}/resolve` - Resolve blocker

### Chat

- `POST /api/projects/{id}/chat` - Chat with Lead Agent

### Activity

- `GET /api/projects/{id}/activity` - Get recent activity log

### WebSocket

- `WS /ws` - Real-time updates
  - Message types: `status_update`, `blocker_resolved`, `task_completed`

## Environment Variables

### Backend (.env)

```bash
# Optional - defaults work for local development
API_HOST=0.0.0.0
API_PORT=8080
```

### Frontend (web-ui/.env.local)

```bash
NEXT_PUBLIC_API_URL=http://localhost:8080
NEXT_PUBLIC_WS_URL=ws://localhost:8080/ws
```

## Production Deployment

### Backend

```bash
# Using uvicorn directly
uvicorn codeframe.ui.server:app --host 0.0.0.0 --port 8080 --workers 4

# Or with gunicorn
gunicorn codeframe.ui.server:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8080
```

### Frontend

```bash
cd web-ui

# Build for production
npm run build

# Start production server
npm start

# Or deploy to Vercel/Netlify
```

## Remote Access (Tailscale)

To access the dashboard remotely:

1. Install Tailscale on the server and client
2. Start Status Server on `0.0.0.0:8080`
3. Access via Tailscale hostname: `http://your-machine.tailnet:8080`

## Troubleshooting

### CORS Errors

The Status Server includes CORS middleware for `localhost:3000` and `localhost:5173`. If using different ports:

```python
# In codeframe/ui/server.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:YOUR_PORT"],
    ...
)
```

### WebSocket Connection Issues

Check that:
1. Status Server is running on port 8080
2. No firewall blocking WebSocket connections
3. Browser console for connection errors

### API 404 Errors

Ensure the Status Server is running and accessible at http://localhost:8080

## Features

### Real-time Updates

The dashboard automatically updates via WebSocket:
- Agent status changes
- Task completions
- Blocker resolutions
- Progress tracking

### Chat Interface

Talk to the Lead Agent directly from the dashboard:
- "How's it going?"
- "What's blocking?"
- "Show me the latest test results"

### Blocker Resolution

Answer questions directly in the UI:
- SYNC blockers highlighted in red (urgent)
- ASYNC blockers in yellow (can wait)
- One-click resolution

### Progress Tracking

- Visual progress bar
- Time tracking (elapsed & remaining)
- Cost tracking (tokens & estimated cost)

## Next Steps

1. Integrate with actual Project/Database layers
2. Add authentication/authorization
3. Implement chat UI component
4. Add more visualizations (charts, graphs)
5. Mobile responsive design
6. Dark mode support
