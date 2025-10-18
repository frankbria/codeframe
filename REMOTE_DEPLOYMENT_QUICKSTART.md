# Remote Staging Server - Quick Start Guide

Deploy CodeFRAME to **frankbria-inspiron-7586** in 3 easy steps.

---

## Quick Deployment (First Time)

### Step 1: Connect and Run Setup Script

```bash
# From your local machine, connect to the remote server
ssh frankbria@frankbria-inspiron-7586

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
# Frontend: http://frankbria-inspiron-7586:14100
# Backend:  http://frankbria-inspiron-7586:14200
```

---

## Daily Operations

### Update and Redeploy

```bash
ssh frankbria@frankbria-inspiron-7586
cd ~/projects/codeframe
git pull origin main
./scripts/deploy-staging.sh
```

### Check Status

```bash
ssh frankbria@frankbria-inspiron-7586
pm2 list
pm2 logs
```

### Restart Services

```bash
ssh frankbria@frankbria-inspiron-7586
pm2 restart all
```

---

## Troubleshooting

### Services not starting?

```bash
# Check logs
pm2 logs --err --lines 50

# Check ports
sudo lsof -i :14100
sudo lsof -i :14200

# Clean restart
pm2 stop all
pm2 delete all
./scripts/deploy-staging.sh
```

### Can't access from network?

```bash
# Verify firewall allows ports
sudo ufw status

# If needed, allow ports
sudo ufw allow 14100/tcp
sudo ufw allow 14200/tcp
```

---

## Full Documentation

See **[docs/REMOTE_STAGING_DEPLOYMENT.md](docs/REMOTE_STAGING_DEPLOYMENT.md)** for complete step-by-step instructions, troubleshooting, and maintenance guides.

---

## Access URLs

- **Frontend**: http://frankbria-inspiron-7586:14100
- **Backend API**: http://frankbria-inspiron-7586:14200

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
