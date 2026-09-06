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

# Derived, never hardcoded: the repo is the parent of the dir holding this script.
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# sudo runs this as root, but the unit must run as the account that owns the repo.
CF_USER="${SUDO_USER:-$(stat -c %U "$PROJECT_ROOT")}"
SERVICE_FILE="$PROJECT_ROOT/systemd/codeframe-health-check.service"
TIMER_FILE="$PROJECT_ROOT/systemd/codeframe-health-check.timer"
SYSTEMD_DIR="/etc/systemd/system"

echo -e "${BLUE}=== CodeFRAME Health Check Timer Installation ===${NC}"
echo "  repo: $PROJECT_ROOT"
echo "  user: $CF_USER"

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
# Escape sed replacement metacharacters (\ & and our | delimiter) so a repo path
# containing one cannot corrupt the unit. Render to a temp file first: writing
# straight to $SYSTEMD_DIR truncates the target before sed runs, so a sed failure
# under `set -e` would leave an empty unit behind.
sed_escape() { printf '%s' "$1" | sed 's/[\\&|]/\\&/g'; }

# systemd opens the StandardOutput/StandardError fds BEFORE ExecStart, and it does
# not create parent directories — so an absent logs/ (untracked, so absent on any
# fresh clone) makes the service fail to spawn at all. health-check.sh's own
# `mkdir -p` runs too late to help.
install -d -m 755 -o "$CF_USER" "$PROJECT_ROOT/logs"

unit_tmp="$(mktemp)"
trap 'rm -f "$unit_tmp"' EXIT
sed -e "s|__CF_USER__|$(sed_escape "$CF_USER")|g" \
    -e "s|__CF_ROOT__|$(sed_escape "$PROJECT_ROOT")|g" \
    "$SERVICE_FILE" > "$unit_tmp"
install -m 644 "$unit_tmp" "$SYSTEMD_DIR/codeframe-health-check.service"
install -m 644 "$TIMER_FILE" "$SYSTEMD_DIR/codeframe-health-check.timer"

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
