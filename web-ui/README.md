# CodeFRAME Web UI

Real-time dashboard for monitoring CodeFRAME autonomous AI agents.

## Tech Stack

- **Next.js 14** - React framework with App Router
- **TypeScript** - Type safety
- **Tailwind CSS** - Styling
- **SWR** - Data fetching with caching
- **WebSocket** - Real-time updates

## Development

```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Open http://localhost:3000
```

## Build

```bash
# Type check
npm run type-check

# Build for production
npm run build

# Start production server
npm start
```

## Architecture

- **src/app/** - Next.js App Router pages
- **src/components/** - React components
- **src/lib/** - API client and WebSocket
- **src/types/** - TypeScript definitions

## API Integration

The UI connects to the FastAPI Status Server (default: localhost:8080) via:
- REST API for data fetching
- WebSocket for real-time updates

Configure the API URL in `.env.local`:
```
NEXT_PUBLIC_API_URL=http://localhost:8080
NEXT_PUBLIC_WS_URL=ws://localhost:8080/ws
```
