#!/usr/bin/env bash
# CodeFRAME Staging Server Startup Script
# This script starts the staging environment using PM2
# For full deployment with dependency installation, use deploy-staging.sh

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Determine project root from script location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo -e "${BLUE}=== CodeFRAME Staging Server Startup ===${NC}"
echo "Project Root: $PROJECT_ROOT"
echo ""

# Check if .env.staging exists
if [ ! -f ".env.staging" ]; then
    echo -e "${RED}Error: .env.staging not found${NC}"
    echo "Please copy .env.staging.example to .env.staging and configure it"
    echo "  cp .env.staging.example .env.staging"
    exit 1
fi

# Load and validate environment
set -a
source .env.staging
set +a

if [ -z "$ANTHROPIC_API_KEY" ] || [ "$ANTHROPIC_API_KEY" = "your-anthropic-api-key-here" ]; then
    echo -e "${RED}Error: ANTHROPIC_API_KEY not configured${NC}"
    exit 1
fi

# Check if PM2 is installed
if ! command -v pm2 &> /dev/null; then
    echo -e "${RED}Error: PM2 not installed${NC}"
    echo "Install with: sudo npm install -g pm2"
    exit 1
fi

# Check if dependencies are installed
if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}Warning: Python virtual environment not found${NC}"
    echo "Run: ./scripts/deploy-staging.sh for full deployment"
    exit 1
fi

if [ ! -d "web-ui/node_modules" ]; then
    echo -e "${YELLOW}Warning: Node.js dependencies not installed${NC}"
    echo "Run: ./scripts/deploy-staging.sh for full deployment"
    exit 1
fi

if [ ! -d "web-ui/.next" ]; then
    echo -e "${YELLOW}Warning: Frontend build not found${NC}"
    echo "Run: ./scripts/deploy-staging.sh for full deployment"
    exit 1
fi

# Ensure logs directory exists
mkdir -p logs

# Check port availability
BACKEND_PORT=${BACKEND_PORT:-14200}
FRONTEND_PORT=${FRONTEND_PORT:-14100}

for port in $FRONTEND_PORT $BACKEND_PORT; do
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo -e "${YELLOW}Warning: Port $port already in use${NC}"
        echo "Stopping existing PM2 processes..."
        pm2 stop all 2>/dev/null || true
        pm2 delete all 2>/dev/null || true
        sleep 2
    fi
done

# Start PM2 ecosystem
echo -e "${BLUE}Starting PM2 processes...${NC}"
pm2 start ecosystem.staging.config.js

# Wait for services to initialize
sleep 5

# Show status
echo -e "${GREEN}Staging server started successfully!${NC}"
echo ""
pm2 list
echo ""
echo -e "${BLUE}Access URLs:${NC}"
echo "  Frontend: http://localhost:$FRONTEND_PORT"
echo "  Backend:  http://localhost:$BACKEND_PORT"
echo ""
echo -e "${BLUE}Useful PM2 commands:${NC}"
echo "  pm2 list         - Show running processes"
echo "  pm2 logs         - View all logs"
echo "  pm2 stop all     - Stop all processes"
echo "  pm2 restart all  - Restart all processes"
echo "  pm2 delete all   - Delete all processes"
