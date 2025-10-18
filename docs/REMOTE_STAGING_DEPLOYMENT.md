# Remote Staging Server Deployment Guide

This guide provides step-by-step instructions for deploying CodeFRAME to a centralized staging server instead of running it locally.

## Server Configuration

Before starting, create your server configuration file:

```bash
# In your local codeframe directory
cp .staging-server.conf.example .staging-server.conf
nano .staging-server.conf
```

Fill in your actual server details:
```bash
STAGING_SERVER_HOST="your-server-hostname"
STAGING_SERVER_USER="your-username"
STAGING_FRONTEND_PORT="14100"
STAGING_BACKEND_PORT="14200"
```

**Note**: `.staging-server.conf` is gitignored and contains your private server details.

Throughout this guide:
- `YOUR_STAGING_SERVER` = your server hostname
- `YOUR_USER` = your SSH username
- Replace these placeholders with your actual values or use the environment variables from `.staging-server.conf`

---

## Prerequisites

Before starting, ensure you have:

1. **SSH access** to your staging server
2. **Git installed** on the remote server
3. **API Keys** (ANTHROPIC_API_KEY, optionally OPENAI_API_KEY)
4. **Network access** to ports 14100 (frontend) and 14200 (backend) on the remote server

---

## Part 1: Initial Server Setup (One-Time)

### Step 1.1: Connect to Remote Server

```bash
# From your local machine
ssh YOUR_USER@YOUR_STAGING_SERVER
```

### Step 1.2: Install System Dependencies

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Install Node.js and npm (required for PM2 and frontend)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Verify Node.js installation
node --version  # Should show v20.x or higher
npm --version   # Should show 10.x or higher

# Install Python 3.11+ (if not already installed)
sudo apt install -y python3.11 python3.11-venv python3-pip

# Install uv (fast Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc  # Reload shell to get uv in PATH

# Verify uv installation
uv --version

# Install PM2 globally (process manager)
sudo npm install -g pm2

# Verify PM2 installation
pm2 --version

# Install lsof (for port checking)
sudo apt install -y lsof
```

### Step 1.3: Create Project Directory

```bash
# Create projects directory if it doesn't exist
mkdir -p ~/projects
cd ~/projects
```

### Step 1.4: Clone Repository

```bash
# Clone the CodeFRAME repository
git clone https://github.com/frankbria/codeframe.git
cd codeframe

# Verify you're on the main branch
git branch
git status
```

---

## Part 2: Environment Configuration

### Step 2.1: Create Staging Environment File

```bash
# Navigate to project root
cd ~/projects/codeframe

# Copy the staging environment template
cp .env.staging.example .env.staging

# Edit the staging environment file
nano .env.staging
```

### Step 2.2: Configure Environment Variables

Update `.env.staging` with the following configuration:

```bash
# === REQUIRED: LLM Provider API Keys ===
ANTHROPIC_API_KEY=sk-ant-api03-YOUR-ACTUAL-KEY-HERE
OPENAI_API_KEY=sk-YOUR-ACTUAL-KEY-HERE  # Optional

# === Server Configuration ===
FRONTEND_PORT=14100
BACKEND_PORT=14200
HOST=0.0.0.0  # Listen on all interfaces for network access

# === Database Configuration ===
DATABASE_PATH=./staging/.codeframe/state.db

# === Logging Configuration ===
LOG_LEVEL=INFO
LOG_FILE=./logs/codeframe.log

# === Environment ===
ENVIRONMENT=staging
```

**Important**:
- Replace `YOUR-ACTUAL-KEY-HERE` with your real API keys
- Save the file (Ctrl+O, Enter, Ctrl+X in nano)
- Verify the file was saved: `cat .env.staging`

### Step 2.3: Verify Environment File Security

```bash
# Set appropriate permissions (prevent unauthorized access to API keys)
chmod 600 .env.staging

# Verify permissions
ls -la .env.staging
# Should show: -rw------- (only owner can read/write)
```

---

## Part 3: Initial Deployment

### Step 3.1: Run Deployment Script

```bash
# Navigate to project root
cd ~/projects/codeframe

# Make deployment script executable
chmod +x scripts/deploy-staging.sh

# Run the deployment script
./scripts/deploy-staging.sh
```

**What this script does**:
1. ✓ Pre-flight checks (uv, npm, pm2 installed)
2. ✓ Environment validation (.env.staging exists and configured)
3. ✓ Port availability check (14100, 14200)
4. ✓ Creates required directories (logs, staging/.codeframe)
5. ✓ Installs Python dependencies with uv
6. ✓ Installs Node.js dependencies
7. ✓ Builds frontend for production
8. ✓ Verifies build artifacts
9. ✓ Starts services with PM2
10. ✓ Health checks (waits for services to respond)

**Expected Output**:
```
╔════════════════════════════════════════════════════════════╗
║          ✅  DEPLOYMENT SUCCESSFUL!                        ║
╚════════════════════════════════════════════════════════════╝

Service Status:
┌────┬────────────────────────────────┬──────────┬──────┬───────────┐
│ id │ name                           │ mode     │ ↺    │ status    │
├────┼────────────────────────────────┼──────────┼──────┼───────────┤
│ 0  │ codeframe-staging-backend      │ fork     │ 0    │ online    │
│ 1  │ codeframe-staging-frontend     │ fork     │ 0    │ online    │
└────┴────────────────────────────────┴──────────┴──────┴───────────┘

Access URLs:
  Frontend: http://localhost:14100
  Backend:  http://localhost:14200
```

### Step 3.2: Verify Services are Running

```bash
# Check PM2 process list
pm2 list

# Check service logs
pm2 logs --lines 50

# Check specific service logs
pm2 logs codeframe-staging-backend --lines 20
pm2 logs codeframe-staging-frontend --lines 20
```

### Step 3.3: Test Local Access on Server

```bash
# Test backend API (should return status info)
curl http://localhost:14200

# Test frontend (should return HTML)
curl http://localhost:14100
```

---

## Part 4: Network Access Setup

### Step 4.1: Configure Firewall (if applicable)

```bash
# Check if ufw firewall is active
sudo ufw status

# If active, allow the required ports
sudo ufw allow 14100/tcp comment 'CodeFRAME Frontend'
sudo ufw allow 14200/tcp comment 'CodeFRAME Backend API'

# Verify rules
sudo ufw status numbered
```

### Step 4.2: Test Remote Access

**From your local machine** (not from the server):

```bash
# Test backend API
curl http://YOUR_STAGING_SERVER:14200

# Open frontend in browser
# Navigate to: http://YOUR_STAGING_SERVER:14100
```

**Expected**: Frontend should load in browser, backend API should return JSON status.

---

## Part 5: Enable Auto-Start on Boot (Optional but Recommended)

### Step 5.1: Save PM2 Process List

```bash
# On the remote server
cd ~/projects/codeframe

# Save current PM2 processes
pm2 save

# Generate PM2 startup script
pm2 startup

# Follow the instructions shown - will be something like:
# sudo env PATH=$PATH:/usr/bin pm2 startup systemd -u YOUR_USER --hp /home/YOUR_USER
# (Copy and run the exact command PM2 outputs)
```

### Step 5.2: Verify Auto-Start Configuration

```bash
# Check PM2 startup status
systemctl status pm2-YOUR_USER

# Test by rebooting (optional)
# sudo reboot
# (Wait for server to reboot, then reconnect and check)
# pm2 list  # Should show services still running
```

---

## Part 6: Ongoing Deployment & Updates

### Step 6.1: Deploy Code Updates

When you push new code to the repository:

```bash
# SSH to remote server
ssh YOUR_USER@YOUR_STAGING_SERVER

# Navigate to project
cd ~/projects/codeframe

# Pull latest changes
git pull origin main

# Redeploy
./scripts/deploy-staging.sh
```

**Tip**: The deployment script automatically:
- Stops existing services
- Rebuilds frontend
- Reinstalls any new dependencies
- Restarts services
- Verifies health

### Step 6.2: Quick Restart (without rebuild)

If you only need to restart services:

```bash
# Restart all services
pm2 restart all

# Restart specific service
pm2 restart codeframe-staging-backend
pm2 restart codeframe-staging-frontend
```

### Step 6.3: View Logs

```bash
# Real-time logs from all services
pm2 logs

# Logs from specific service
pm2 logs codeframe-staging-backend
pm2 logs codeframe-staging-frontend

# Last 100 lines
pm2 logs --lines 100

# Error logs only
pm2 logs --err

# Log files are also saved to:
# ~/projects/codeframe/logs/backend-error.log
# ~/projects/codeframe/logs/backend-out.log
# ~/projects/codeframe/logs/frontend-error.log
# ~/projects/codeframe/logs/frontend-out.log
```

---

## Part 7: Common PM2 Commands

```bash
# List all processes
pm2 list

# Show detailed info about a process
pm2 show codeframe-staging-backend

# Monitor in real-time (CPU, memory, logs)
pm2 monit

# Stop all services
pm2 stop all

# Stop specific service
pm2 stop codeframe-staging-backend

# Restart all services
pm2 restart all

# Delete all processes (stops and removes from PM2)
pm2 delete all

# View PM2 logs
pm2 logs

# Flush all logs
pm2 flush
```

---

## Part 8: Troubleshooting

### Issue: Services won't start

**Check logs**:
```bash
pm2 logs --err --lines 50
```

**Common causes**:
1. **Port already in use**:
   ```bash
   # Find process using the port
   sudo lsof -i :14100
   sudo lsof -i :14200

   # Kill the process
   kill -9 <PID>

   # Then restart
   pm2 restart all
   ```

2. **Missing API keys**:
   ```bash
   # Verify .env.staging has valid keys
   grep ANTHROPIC_API_KEY .env.staging

   # If not configured, edit:
   nano .env.staging

   # Then restart
   pm2 restart all
   ```

3. **Build failed**:
   ```bash
   # Rebuild manually
   cd web-ui
   npm run build
   cd ..
   pm2 restart all
   ```

### Issue: Cannot access from network

**Check firewall**:
```bash
# Verify ports are open
sudo ufw status

# If not, allow them
sudo ufw allow 14100/tcp
sudo ufw allow 14200/tcp
```

**Verify services are listening on all interfaces**:
```bash
# Should show 0.0.0.0:14100 and 0.0.0.0:14200
sudo netstat -tlnp | grep -E '14100|14200'
```

### Issue: Services crash after running for a while

**Check memory usage**:
```bash
pm2 list  # Shows memory usage

# If memory is high, restart
pm2 restart all
```

**Enable auto-restart on memory limit** (already configured in ecosystem.staging.config.js):
- Backend: max 500MB
- Frontend: max 500MB

### Issue: Old processes still running

**Clean restart**:
```bash
# Stop all PM2 processes
pm2 stop all

# Delete all PM2 processes
pm2 delete all

# Kill any lingering Node.js processes
pkill -9 node

# Kill any lingering Python processes for codeframe
pkill -f "codeframe.ui.server"

# Redeploy
./scripts/deploy-staging.sh
```

---

## Part 9: Security Best Practices

1. **Protect API Keys**:
   ```bash
   # Ensure .env.staging is not world-readable
   chmod 600 .env.staging

   # Ensure it's in .gitignore
   grep ".env.staging" .gitignore
   ```

2. **Firewall Configuration**:
   ```bash
   # Only allow access from trusted networks
   # Or use SSH tunneling for access
   ```

3. **Regular Updates**:
   ```bash
   # Update system packages monthly
   sudo apt update && sudo apt upgrade -y

   # Update Node.js packages
   cd ~/projects/codeframe/web-ui
   npm update

   # Update Python packages
   cd ~/projects/codeframe
   uv sync
   ```

---

## Part 10: Monitoring & Maintenance

### Daily Checks

```bash
# Quick status check
pm2 list

# Memory/CPU usage
pm2 monit  # Press Ctrl+C to exit
```

### Weekly Maintenance

```bash
# Check logs for errors
pm2 logs --err --lines 100

# Rotate/clear old logs
pm2 flush

# Check disk space
df -h
```

### Monthly Maintenance

```bash
# Update dependencies
cd ~/projects/codeframe
git pull origin main
./scripts/deploy-staging.sh

# Clean up old PM2 logs
pm2 flush
```

---

## Part 11: Reverting to Local Development

If you need to go back to running locally:

```bash
# On your local machine
cd ~/projects/codeframe

# Use the local deployment script
./scripts/deploy-staging.sh

# Or run directly with PM2
pm2 start ecosystem.staging.config.js
```

---

## Summary Checklist

- [ ] SSH access to YOUR_STAGING_SERVER confirmed
- [ ] System dependencies installed (Node.js, uv, PM2)
- [ ] Repository cloned to ~/projects/codeframe
- [ ] .env.staging configured with valid API keys
- [ ] Deployment script executed successfully
- [ ] Services running (pm2 list shows online)
- [ ] Local access verified (curl http://localhost:14100)
- [ ] Remote access verified (browser to http://YOUR_STAGING_SERVER:14100)
- [ ] Firewall configured (if applicable)
- [ ] PM2 auto-start enabled (optional)
- [ ] Monitoring commands tested

---

## Quick Reference Card

```bash
# ============================================
# DEPLOYMENT
# ============================================
ssh YOUR_USER@YOUR_STAGING_SERVER
cd ~/projects/codeframe
git pull origin main
./scripts/deploy-staging.sh

# ============================================
# MONITORING
# ============================================
pm2 list                    # List processes
pm2 logs                    # View logs
pm2 monit                   # Real-time monitoring

# ============================================
# MANAGEMENT
# ============================================
pm2 restart all             # Restart services
pm2 stop all                # Stop services
pm2 delete all              # Remove services

# ============================================
# TROUBLESHOOTING
# ============================================
pm2 logs --err --lines 50   # View errors
sudo lsof -i :14100         # Check port usage
sudo lsof -i :14200

# ============================================
# ACCESS URLS
# ============================================
Frontend: http://YOUR_STAGING_SERVER:14100
Backend:  http://YOUR_STAGING_SERVER:14200
```

---

## Getting Help

- **Repository**: https://github.com/frankbria/codeframe
- **Issues**: https://github.com/frankbria/codeframe/issues
- **Documentation**: ~/projects/codeframe/docs/

---

**Deployment Guide Version**: 1.0
**Last Updated**: 2025-10-17
**Target Server**: YOUR_STAGING_SERVER
