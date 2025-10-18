# Remote Staging Server - Quick Start Guide

Deploy CodeFRAME to your remote staging server in 3 easy steps.

---

## Prerequisites

### Configure Your Server Details

Copy the example configuration file and fill in your server details:

```bash
# In your local codeframe directory
cp .staging-server.conf.example .staging-server.conf
nano .staging-server.conf
```

Example `.staging-server.conf`:
```bash
STAGING_SERVER_HOST="staging-box.local"
STAGING_SERVER_USER="deploy"
STAGING_FRONTEND_PORT="14100"
STAGING_BACKEND_PORT="14200"
```

**Note**: `.staging-server.conf` is gitignored and will not be committed to the repository.

---

## Quick Deployment (First Time)

### Step 1: Connect and Run Setup Script

```bash
# Load your server configuration
source .staging-server.conf

# Connect to the remote server
ssh ${STAGING_SERVER_SSH}

# Run the automated setup script
curl -fsSL https://raw.githubusercontent.com/frankbria/codeframe/main/scripts/remote-setup.sh | bash

# Or if you already have the repo cloned:
cd ~/projects/codeframe
./scripts/remote-setup.sh
```

This installs all dependencies and sets up the project directory.

### Step 2: Configure API Keys

```bash
# Edit the environment file
cd ~/projects/codeframe
nano .env.staging

# Set your API key:
ANTHROPIC_API_KEY=sk-ant-api03-YOUR-KEY-HERE

# Save: Ctrl+O, Enter, Ctrl+X
```

### Step 3: Deploy

```bash
# Run deployment script
./scripts/deploy-staging.sh

# Wait for success message, then access:
# Frontend: http://${STAGING_SERVER_HOST}:${STAGING_FRONTEND_PORT}
# Backend:  http://${STAGING_SERVER_HOST}:${STAGING_BACKEND_PORT}
```

---

## Daily Operations

### Update and Redeploy

```bash
# Load your server configuration
source .staging-server.conf

ssh ${STAGING_SERVER_SSH}
cd ~/projects/codeframe
git pull origin main
./scripts/deploy-staging.sh
```

### Check Status

```bash
source .staging-server.conf
ssh ${STAGING_SERVER_SSH}
pm2 list
pm2 logs
```

### Restart Services

```bash
source .staging-server.conf
ssh ${STAGING_SERVER_SSH}
pm2 restart all
```

---

## Troubleshooting

### Services not starting?

```bash
# Check logs
pm2 logs --err --lines 50

# Check ports (use your configured ports)
source .staging-server.conf
sudo lsof -i :${STAGING_FRONTEND_PORT}
sudo lsof -i :${STAGING_BACKEND_PORT}

# Clean restart
pm2 stop all
pm2 delete all
./scripts/deploy-staging.sh
```

### Can't access from network?

```bash
source .staging-server.conf

# Verify firewall allows ports
sudo ufw status

# If needed, allow ports
sudo ufw allow ${STAGING_FRONTEND_PORT}/tcp
sudo ufw allow ${STAGING_BACKEND_PORT}/tcp
```

---

## Full Documentation

See **[docs/REMOTE_STAGING_DEPLOYMENT.md](docs/REMOTE_STAGING_DEPLOYMENT.md)** for complete step-by-step instructions, troubleshooting, and maintenance guides.

---

## Access URLs

After sourcing `.staging-server.conf`:

- **Frontend**: `http://${STAGING_SERVER_HOST}:${STAGING_FRONTEND_PORT}`
- **Backend API**: `http://${STAGING_SERVER_HOST}:${STAGING_BACKEND_PORT}`

---

## Quick PM2 Commands

```bash
pm2 list              # Show all processes
pm2 logs              # View logs in real-time
pm2 restart all       # Restart all services
pm2 stop all          # Stop all services
pm2 monit             # Monitor CPU/memory
```

---

**Need Help?** Check [docs/REMOTE_STAGING_DEPLOYMENT.md](docs/REMOTE_STAGING_DEPLOYMENT.md)
