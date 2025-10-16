#!/usr/bin/env bash
# Install CodeFRAME Staging Server Health Check systemd timer
# This script must be run with sudo privileges

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PROJECT_ROOT="/home/frankbria/projects/codeframe"
SERVICE_FILE="$PROJECT_ROOT/systemd/codeframe-health-check.service"
TIMER_FILE="$PROJECT_ROOT/systemd/codeframe-health-check.timer"
SYSTEMD_DIR="/etc/systemd/system"

echo -e "${BLUE}=== CodeFRAME Health Check Timer Installation ===${NC}"

# Check if running with sudo
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Error: This script must be run with sudo${NC}"
    echo "Usage: sudo ./scripts/install-health-check.sh"
    exit 1
fi

# Check if service and timer files exist
if [ ! -f "$SERVICE_FILE" ]; then
    echo -e "${RED}Error: Service file not found at $SERVICE_FILE${NC}"
    exit 1
fi

if [ ! -f "$TIMER_FILE" ]; then
    echo -e "${RED}Error: Timer file not found at $TIMER_FILE${NC}"
    exit 1
fi

# Copy service and timer files to systemd directory
echo -e "${BLUE}Installing systemd files...${NC}"
cp "$SERVICE_FILE" "$SYSTEMD_DIR/codeframe-health-check.service"
cp "$TIMER_FILE" "$SYSTEMD_DIR/codeframe-health-check.timer"
chmod 644 "$SYSTEMD_DIR/codeframe-health-check.service"
chmod 644 "$SYSTEMD_DIR/codeframe-health-check.timer"

# Reload systemd daemon
echo -e "${BLUE}Reloading systemd daemon...${NC}"
systemctl daemon-reload

# Enable and start timer
echo -e "${BLUE}Enabling and starting health check timer...${NC}"
systemctl enable codeframe-health-check.timer
systemctl start codeframe-health-check.timer

echo -e "${GREEN}✓ Health check timer installed successfully!${NC}"
echo ""
echo -e "${BLUE}Timer Status:${NC}"
systemctl status codeframe-health-check.timer --no-pager
echo ""
echo -e "${BLUE}Next scheduled run:${NC}"
systemctl list-timers codeframe-health-check.timer --no-pager
echo ""
echo -e "${BLUE}Management Commands:${NC}"
echo "  sudo systemctl start codeframe-health-check.service  - Run health check now"
echo "  sudo systemctl status codeframe-health-check.timer   - Check timer status"
echo "  sudo systemctl stop codeframe-health-check.timer     - Stop timer"
echo "  sudo systemctl disable codeframe-health-check.timer  - Disable autostart"
echo "  sudo journalctl -u codeframe-health-check -f         - View health check logs"
echo ""
echo -e "${BLUE}Health check will run:${NC}"
echo "  - Daily at 2:00 AM"
echo "  - 15 minutes after system boot"
echo "  - Can be triggered manually anytime"
