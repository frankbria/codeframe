#!/usr/bin/env bash
# CodeFRAME Staging Server Startup Script
# This script starts the staging environment using PM2

set -e

# Colors for output
GREEN='\033[0.32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Project root directory
PROJECT_ROOT="/home/frankbria/projects/codeframe"
cd "$PROJECT_ROOT"

echo -e "${BLUE}=== CodeFRAME Staging Server Startup ===${NC}"

# Check if .env.staging exists
if [ ! -f ".env.staging" ]; then
    echo -e "${RED}Error: .env.staging not found${NC}"
    echo "Please copy .env.staging.example to .env.staging and configure it"
    exit 1
fi

# Check if PM2 is installed
if ! command -v pm2 &> /dev/null; then
    echo -e "${RED}Error: PM2 not installed${NC}"
    echo "Run: sudo npm install -g pm2"
    exit 1
fi

# Start PM2 ecosystem
echo -e "${BLUE}Starting PM2 processes...${NC}"
pm2 start ecosystem.staging.config.js

# Show status
echo -e "${GREEN}Staging server started successfully!${NC}"
echo ""
pm2 list
echo ""
echo -e "${BLUE}Access URLs:${NC}"
echo "Frontend: http://localhost:14100"
echo "Backend:  http://localhost:14200"
echo ""
echo -e "${BLUE}Useful PM2 commands:${NC}"
echo "  pm2 list         - Show running processes"
echo "  pm2 logs         - View all logs"
echo "  pm2 stop all     - Stop all processes"
echo "  pm2 restart all  - Restart all processes"
echo "  pm2 delete all   - Delete all processes"