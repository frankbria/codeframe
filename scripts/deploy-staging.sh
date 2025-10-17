#!/usr/bin/env bash
# CodeFRAME Complete Staging Deployment Script
# This script handles the full deployment workflow with validation and error handling

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

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   CodeFRAME Staging Deployment - Comprehensive Setup      ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "Project Root: $PROJECT_ROOT"
echo ""

# ============================================================================
# PHASE 1: PRE-FLIGHT CHECKS
# ============================================================================
echo -e "${BLUE}[1/10] Pre-flight Checks${NC}"

# Check required commands
for cmd in uv npm pm2; do
    if ! command -v $cmd &> /dev/null; then
        echo -e "${RED}✗ Error: $cmd not installed${NC}"
        echo "Install with:"
        case $cmd in
            uv) echo "  curl -LsSf https://astral.sh/uv/install.sh | sh" ;;
            npm) echo "  Install Node.js from https://nodejs.org/" ;;
            pm2) echo "  sudo npm install -g pm2" ;;
        esac
        exit 1
    fi
    echo -e "${GREEN}✓ $cmd is installed${NC}"
done

# ============================================================================
# PHASE 2: ENVIRONMENT VALIDATION
# ============================================================================
echo ""
echo -e "${BLUE}[2/10] Environment Validation${NC}"

# Check if .env.staging exists
if [ ! -f ".env.staging" ]; then
    echo -e "${RED}✗ Error: .env.staging not found${NC}"
    echo "Please copy .env.staging.example to .env.staging and configure it:"
    echo "  cp .env.staging.example .env.staging"
    echo "  # Edit .env.staging with your actual values"
    exit 1
fi
echo -e "${GREEN}✓ .env.staging exists${NC}"

# Load and validate environment variables
set -a
source .env.staging
set +a

if [ -z "$ANTHROPIC_API_KEY" ] || [ "$ANTHROPIC_API_KEY" = "your-anthropic-api-key-here" ]; then
    echo -e "${RED}✗ Error: ANTHROPIC_API_KEY not configured in .env.staging${NC}"
    echo "Please edit .env.staging and set a valid ANTHROPIC_API_KEY"
    exit 1
fi
echo -e "${GREEN}✓ ANTHROPIC_API_KEY is configured${NC}"

# ============================================================================
# PHASE 3: PORT AVAILABILITY CHECK
# ============================================================================
echo ""
echo -e "${BLUE}[3/10] Port Availability Check${NC}"

BACKEND_PORT=${BACKEND_PORT:-14200}
FRONTEND_PORT=${FRONTEND_PORT:-14100}

for port in $FRONTEND_PORT $BACKEND_PORT; do
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo -e "${YELLOW}⚠ Warning: Port $port already in use${NC}"
        echo "Attempting to stop existing services..."
        pm2 stop all 2>/dev/null || true
        pm2 delete all 2>/dev/null || true
        sleep 2

        if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
            echo -e "${RED}✗ Error: Port $port still in use after stopping PM2${NC}"
            echo "Please manually stop the process using port $port"
            exit 1
        fi
    fi
    echo -e "${GREEN}✓ Port $port is available${NC}"
done

# ============================================================================
# PHASE 4: CREATE REQUIRED DIRECTORIES
# ============================================================================
echo ""
echo -e "${BLUE}[4/10] Creating Required Directories${NC}"

mkdir -p logs
mkdir -p staging/.codeframe
echo -e "${GREEN}✓ Created logs/ directory${NC}"
echo -e "${GREEN}✓ Created staging/.codeframe/ directory${NC}"

# ============================================================================
# PHASE 5: INSTALL PYTHON DEPENDENCIES
# ============================================================================
echo ""
echo -e "${BLUE}[5/10] Installing Python Dependencies${NC}"

if [ ! -d ".venv" ]; then
    echo "Creating Python virtual environment..."
    uv venv
fi

echo "Syncing Python dependencies with uv..."
uv sync
echo -e "${GREEN}✓ Python dependencies installed${NC}"

# ============================================================================
# PHASE 6: INSTALL NODE.JS DEPENDENCIES
# ============================================================================
echo ""
echo -e "${BLUE}[6/10] Installing Node.js Dependencies${NC}"

# Install dotenv for PM2 ecosystem config
echo "Installing dotenv for PM2 config..."
npm install dotenv

cd web-ui
echo "Installing Node.js dependencies (this may take a minute)..."
npm ci --production=false
cd ..
echo -e "${GREEN}✓ Node.js dependencies installed${NC}"

# ============================================================================
# PHASE 7: BUILD FRONTEND FOR PRODUCTION
# ============================================================================
echo ""
echo -e "${BLUE}[7/10] Building Frontend for Production${NC}"

cd web-ui
echo "Building Next.js application (this may take a minute)..."
npm run build
cd ..
echo -e "${GREEN}✓ Frontend built successfully${NC}"

# ============================================================================
# PHASE 8: VERIFY BUILD ARTIFACTS
# ============================================================================
echo ""
echo -e "${BLUE}[8/10] Verifying Build Artifacts${NC}"

# Verify Python package is importable
if ! .venv/bin/python -c "import codeframe" 2>/dev/null; then
    echo -e "${RED}✗ Error: codeframe package not properly installed${NC}"
    echo "The Python package cannot be imported. Check the installation."
    exit 1
fi
echo -e "${GREEN}✓ Python package is importable${NC}"

# Verify Next.js build exists
if [ ! -d "web-ui/.next" ]; then
    echo -e "${RED}✗ Error: Frontend build missing${NC}"
    echo "The web-ui/.next directory was not created during build."
    exit 1
fi
echo -e "${GREEN}✓ Frontend build artifacts exist${NC}"

# Verify virtual environment Python executable
if [ ! -x ".venv/bin/python" ]; then
    echo -e "${RED}✗ Error: Python virtual environment executable not found${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Python virtual environment is valid${NC}"

# ============================================================================
# PHASE 9: START SERVICES WITH PM2
# ============================================================================
echo ""
echo -e "${BLUE}[9/10] Starting Services with PM2${NC}"

# Stop any existing processes
echo "Stopping existing PM2 processes..."
pm2 stop all 2>/dev/null || true
pm2 delete all 2>/dev/null || true
sleep 2

# Start services
echo "Starting services..."
pm2 start ecosystem.staging.config.js

# Give services a moment to initialize
sleep 5

echo -e "${GREEN}✓ PM2 services started${NC}"

# ============================================================================
# PHASE 10: HEALTH CHECK
# ============================================================================
echo ""
echo -e "${BLUE}[10/10] Health Check${NC}"

# Function to wait for service with timeout
wait_for_service() {
    local port=$1
    local service_name=$2
    local timeout=60
    local elapsed=0

    echo "Waiting for $service_name (port $port) to be ready..."

    while [ $elapsed -lt $timeout ]; do
        if curl -sf "http://localhost:$port" >/dev/null 2>&1; then
            echo -e "${GREEN}✓ $service_name is responding${NC}"
            return 0
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done

    echo -e "${RED}✗ $service_name failed to start within ${timeout}s${NC}"
    return 1
}

# Check backend
if ! wait_for_service "$BACKEND_PORT" "Backend"; then
    echo ""
    echo -e "${RED}Backend startup failed. Checking logs...${NC}"
    pm2 logs codeframe-staging-backend --lines 20 --nostream
    exit 1
fi

# Check frontend
if ! wait_for_service "$FRONTEND_PORT" "Frontend"; then
    echo ""
    echo -e "${RED}Frontend startup failed. Checking logs...${NC}"
    pm2 logs codeframe-staging-frontend --lines 20 --nostream
    exit 1
fi

# ============================================================================
# DEPLOYMENT COMPLETE
# ============================================================================
echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║          ✅  DEPLOYMENT SUCCESSFUL!                        ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}Service Status:${NC}"
pm2 list
echo ""
echo -e "${BLUE}Access URLs:${NC}"
echo "  Frontend: http://localhost:$FRONTEND_PORT"
echo "  Backend:  http://localhost:$BACKEND_PORT"
echo ""
echo -e "${BLUE}Useful PM2 Commands:${NC}"
echo "  pm2 list              - Show running processes"
echo "  pm2 logs              - View all logs"
echo "  pm2 logs --lines 100  - View last 100 log lines"
echo "  pm2 stop all          - Stop all processes"
echo "  pm2 restart all       - Restart all processes"
echo "  pm2 delete all        - Delete all processes"
echo ""
echo -e "${BLUE}Log Files:${NC}"
echo "  Backend:  $PROJECT_ROOT/logs/backend-error.log"
echo "  Frontend: $PROJECT_ROOT/logs/frontend-error.log"
echo ""
