#!/usr/bin/env bash
# CodeFRAME Remote Server Initial Setup Script
# Run this script on the remote server (YOUR_STAGING_SERVER) for first-time setup

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   CodeFRAME Remote Server Initial Setup                   ║${NC}"
echo -e "${BLUE}║   Target: YOUR_STAGING_SERVER                          ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# ============================================================================
# PHASE 1: SYSTEM DEPENDENCIES
# ============================================================================
echo -e "${BLUE}[1/5] Installing System Dependencies${NC}"
echo ""

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    echo -e "${RED}✗ Do not run this script as root or with sudo${NC}"
    echo "Run as: ./scripts/remote-setup.sh"
    exit 1
fi

# Update package lists
echo "Updating package lists..."
sudo apt update

# Install Node.js 20.x if not already installed
if ! command -v node &> /dev/null || ! node --version | grep -q "v20"; then
    echo "Installing Node.js 20.x..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt install -y nodejs
    echo -e "${GREEN}✓ Node.js installed${NC}"
else
    echo -e "${GREEN}✓ Node.js already installed${NC}"
fi

# Verify Node.js version
NODE_VERSION=$(node --version)
echo "  Node.js version: $NODE_VERSION"

# Install Python 3.11+ if not already installed
if ! command -v python3.11 &> /dev/null; then
    echo "Installing Python 3.11..."
    sudo apt install -y python3.11 python3.11-venv python3-pip
    echo -e "${GREEN}✓ Python 3.11 installed${NC}"
else
    echo -e "${GREEN}✓ Python 3.11 already installed${NC}"
fi

# Verify Python version
PYTHON_VERSION=$(python3.11 --version)
echo "  Python version: $PYTHON_VERSION"

# Install uv if not already installed
if ! command -v uv &> /dev/null; then
    echo "Installing uv (Python package manager)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # Add uv to PATH for current session
    export PATH="$HOME/.cargo/bin:$PATH"

    echo -e "${GREEN}✓ uv installed${NC}"
else
    echo -e "${GREEN}✓ uv already installed${NC}"
fi

# Verify uv installation
UV_VERSION=$(uv --version 2>/dev/null || echo "not found")
echo "  uv version: $UV_VERSION"

# Install PM2 globally if not already installed
if ! command -v pm2 &> /dev/null; then
    echo "Installing PM2 (process manager)..."
    sudo npm install -g pm2
    echo -e "${GREEN}✓ PM2 installed${NC}"
else
    echo -e "${GREEN}✓ PM2 already installed${NC}"
fi

# Verify PM2 installation
PM2_VERSION=$(pm2 --version)
echo "  PM2 version: $PM2_VERSION"

# Install lsof for port checking
if ! command -v lsof &> /dev/null; then
    echo "Installing lsof..."
    sudo apt install -y lsof
    echo -e "${GREEN}✓ lsof installed${NC}"
else
    echo -e "${GREEN}✓ lsof already installed${NC}"
fi

# ============================================================================
# PHASE 2: PROJECT DIRECTORY SETUP
# ============================================================================
echo ""
echo -e "${BLUE}[2/5] Setting Up Project Directory${NC}"
echo ""

# Create projects directory if it doesn't exist
mkdir -p ~/projects
echo -e "${GREEN}✓ Created ~/projects directory${NC}"

# Check if codeframe repo already exists
if [ -d ~/projects/codeframe ]; then
    echo -e "${YELLOW}⚠ ~/projects/codeframe already exists${NC}"
    read -p "Do you want to update it? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        cd ~/projects/codeframe
        git pull origin main
        echo -e "${GREEN}✓ Repository updated${NC}"
    else
        echo "Skipping repository clone."
    fi
else
    echo "Cloning CodeFRAME repository..."
    cd ~/projects
    git clone https://github.com/frankbria/codeframe.git
    echo -e "${GREEN}✓ Repository cloned${NC}"
fi

cd ~/projects/codeframe

# ============================================================================
# PHASE 3: ENVIRONMENT CONFIGURATION
# ============================================================================
echo ""
echo -e "${BLUE}[3/5] Environment Configuration${NC}"
echo ""

# Check if .env.staging exists
if [ ! -f .env.staging ]; then
    if [ -f .env.staging.example ]; then
        echo "Creating .env.staging from template..."
        cp .env.staging.example .env.staging
        chmod 600 .env.staging
        echo -e "${GREEN}✓ Created .env.staging${NC}"

        echo ""
        echo -e "${YELLOW}════════════════════════════════════════════════════════════${NC}"
        echo -e "${YELLOW}   IMPORTANT: You must now configure your API keys!${NC}"
        echo -e "${YELLOW}════════════════════════════════════════════════════════════${NC}"
        echo ""
        echo "Edit .env.staging and set your ANTHROPIC_API_KEY:"
        echo "  nano .env.staging"
        echo ""
        echo "Then re-run this script or continue to deployment."
        echo ""

        read -p "Do you want to edit .env.staging now? (Y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Nn]$ ]]; then
            nano .env.staging
        fi
    else
        echo -e "${RED}✗ .env.staging.example not found${NC}"
        echo "Please create .env.staging manually with required configuration."
        exit 1
    fi
else
    echo -e "${GREEN}✓ .env.staging already exists${NC}"

    # Check if API key is configured
    if grep -q "your-anthropic-api-key-here" .env.staging 2>/dev/null; then
        echo -e "${YELLOW}⚠ Warning: ANTHROPIC_API_KEY appears to be unconfigured${NC}"
        read -p "Do you want to edit .env.staging now? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            nano .env.staging
        fi
    else
        echo -e "${GREEN}✓ ANTHROPIC_API_KEY appears to be configured${NC}"
    fi
fi

# Ensure proper permissions
chmod 600 .env.staging
echo -e "${GREEN}✓ Set .env.staging permissions to 600${NC}"

# ============================================================================
# PHASE 4: FIREWALL CONFIGURATION (OPTIONAL)
# ============================================================================
echo ""
echo -e "${BLUE}[4/5] Firewall Configuration${NC}"
echo ""

# Check if ufw is active
if sudo ufw status | grep -q "Status: active"; then
    echo "UFW firewall is active."

    # Check if ports are already allowed
    if ! sudo ufw status | grep -q "14100/tcp"; then
        read -p "Allow port 14100 (frontend) through firewall? (Y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Nn]$ ]]; then
            sudo ufw allow 14100/tcp comment 'CodeFRAME Frontend'
            echo -e "${GREEN}✓ Port 14100 allowed${NC}"
        fi
    else
        echo -e "${GREEN}✓ Port 14100 already allowed${NC}"
    fi

    if ! sudo ufw status | grep -q "14200/tcp"; then
        read -p "Allow port 14200 (backend) through firewall? (Y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Nn]$ ]]; then
            sudo ufw allow 14200/tcp comment 'CodeFRAME Backend API'
            echo -e "${GREEN}✓ Port 14200 allowed${NC}"
        fi
    else
        echo -e "${GREEN}✓ Port 14200 already allowed${NC}"
    fi
else
    echo "UFW firewall is not active. Skipping firewall configuration."
fi

# ============================================================================
# PHASE 5: READY TO DEPLOY
# ============================================================================
echo ""
echo -e "${BLUE}[5/5] Setup Complete${NC}"
echo ""

echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║          ✅  INITIAL SETUP SUCCESSFUL!                     ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${BLUE}System Dependencies Installed:${NC}"
echo "  ✓ Node.js $NODE_VERSION"
echo "  ✓ Python $PYTHON_VERSION"
echo "  ✓ uv $UV_VERSION"
echo "  ✓ PM2 $PM2_VERSION"
echo "  ✓ lsof"
echo ""

echo -e "${BLUE}Project Setup:${NC}"
echo "  ✓ Repository: ~/projects/codeframe"
echo "  ✓ Environment: .env.staging configured"
echo ""

echo -e "${BLUE}Next Steps:${NC}"
echo ""
echo "1. Verify your .env.staging configuration:"
echo "   cat .env.staging | grep ANTHROPIC_API_KEY"
echo ""
echo "2. Run the deployment script:"
echo "   cd ~/projects/codeframe"
echo "   ./scripts/deploy-staging.sh"
echo ""
echo "3. After deployment, access the dashboard:"
echo "   Frontend: http://YOUR_STAGING_SERVER:14100"
echo "   Backend:  http://YOUR_STAGING_SERVER:14200"
echo ""
echo "4. (Optional) Enable auto-start on boot:"
echo "   pm2 save"
echo "   pm2 startup"
echo ""

echo -e "${BLUE}Documentation:${NC}"
echo "  See docs/REMOTE_STAGING_DEPLOYMENT.md for full guide"
echo ""
