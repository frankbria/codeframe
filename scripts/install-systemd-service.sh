#!/usr/bin/env bash
# Install CodeFRAME Staging Server systemd service
# This script must be run with sudo privileges

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PROJECT_ROOT="/home/frankbria/projects/codeframe"
SERVICE_FILE="$PROJECT_ROOT/systemd/codeframe-staging.service"
SYSTEMD_DIR="/etc/systemd/system"

echo -e "${BLUE}=== CodeFRAME Staging Server systemd Installation ===${NC}"

# Check if running with sudo
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Error: This script must be run with sudo${NC}"
    echo "Usage: sudo ./scripts/install-systemd-service.sh"
    exit 1
fi

# Check if service file exists
if [ ! -f "$SERVICE_FILE" ]; then
    echo -e "${RED}Error: Service file not found at $SERVICE_FILE${NC}"
    exit 1
fi

# Check if .env.staging exists
if [ ! -f "$PROJECT_ROOT/.env.staging" ]; then
    echo -e "${YELLOW}Warning: .env.staging not found${NC}"
    echo "Please create .env.staging from .env.staging.example before starting the service"
fi

# Copy service file to systemd directory
echo -e "${BLUE}Installing service file...${NC}"
cp "$SERVICE_FILE" "$SYSTEMD_DIR/codeframe-staging.service"
chmod 644 "$SYSTEMD_DIR/codeframe-staging.service"

# Reload systemd daemon
echo -e "${BLUE}Reloading systemd daemon...${NC}"
systemctl daemon-reload

# Enable service to start on boot
echo -e "${BLUE}Enabling service to start on boot...${NC}"
systemctl enable codeframe-staging.service

echo -e "${GREEN}✓ systemd service installed successfully!${NC}"
echo ""
echo -e "${BLUE}Service Management Commands:${NC}"
echo "  sudo systemctl start codeframe-staging    - Start the service"
echo "  sudo systemctl stop codeframe-staging     - Stop the service"
echo "  sudo systemctl restart codeframe-staging  - Restart the service"
echo "  sudo systemctl status codeframe-staging   - Check service status"
echo "  sudo systemctl disable codeframe-staging  - Disable autostart"
echo "  sudo journalctl -u codeframe-staging -f   - View service logs"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo "1. Ensure .env.staging is configured with ANTHROPIC_API_KEY"
echo "2. Start the service: sudo systemctl start codeframe-staging"
echo "3. Check status: sudo systemctl status codeframe-staging"
