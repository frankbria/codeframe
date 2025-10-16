# CodeFRAME Staging Server Setup

Complete guide for setting up and managing the CodeFRAME staging server on WSL for manual testing and network access.

## Architecture Overview

**Technology Stack:**
- **Process Manager**: PM2 (manages both backend and frontend processes)
- **Backend**: FastAPI Status Server (Python, port 8000)
- **Frontend**: Vite/React Web UI (Node.js, port 3000)
- **Database**: SQLite (file-based, persistent)
- **Platform**: WSL2 (Windows Subsystem for Linux)

**Key Features:**
- Auto-restart on process crash
- Persistent across WSL restarts (with manual startup)
- Accessible from Windows host, LAN, and Tailscale
- Centralized logging
- Isolated from development environment

## Quick Start

### 1. Initial Setup

```bash
# Navigate to project
cd /home/frankbria/projects/codeframe

# Copy and configure environment file
cp .env.staging.example .env.staging
# Edit .env.staging and add your ANTHROPIC_API_KEY
nano .env.staging

# Option A: Manual start (test first)
./scripts/start-staging.sh

# Option B: Install systemd service (auto-start on WSL boot)
sudo ./scripts/install-systemd-service.sh

# Option C: Install health monitoring (daily checks + auto-recovery)
sudo ./scripts/install-health-check.sh
```

### 1a. Windows Autostart (Optional)

For automatic startup when Windows boots, see `scripts/WINDOWS_AUTOSTART_SETUP.md`

### 2. Access URLs

**From Windows Host:**
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

**From LAN (other devices on network):**
- Frontend: http://<WSL_IP>:3000
- Backend API: http://<WSL_IP>:8000

Get WSL IP: `ip addr show eth0 | grep 'inet ' | awk '{print $2}' | cut -d/ -f1`

**From Tailscale (remote access):**
- Use Windows host's Tailscale IP
- Ports automatically forwarded from WSL to Windows

## Detailed Setup Guide

### Prerequisites

1. **WSL2 with Ubuntu** (already installed)
2. **Node.js and npm** (already installed: v22.20.0, npm 10.9.3)
3. **Python 3.13+** (already installed)
4. **PM2** (install globally: `sudo npm install -g pm2`)

### Environment Configuration

Create `.env.staging` from the template:

```bash
# CodeFRAME Staging Environment Configuration
ANTHROPIC_API_KEY=your-actual-api-key-here
DATABASE_PATH=/home/frankbria/projects/codeframe/staging/.codeframe/state.db
BACKEND_PORT=8000
FRONTEND_PORT=3000
HOST=0.0.0.0
NODE_ENV=staging
PYTHON_ENV=staging
LOG_LEVEL=INFO
```

### PM2 Process Management

**Install PM2 globally (first time only):**
```bash
sudo npm install -g pm2
```

**Start Services:**
```bash
./scripts/start-staging.sh
# OR
pm2 start ecosystem.staging.config.js
```

**View Running Processes:**
```bash
pm2 list
```

**View Logs:**
```bash
# All logs (combined)
pm2 logs

# Backend logs only
pm2 logs codeframe-backend-staging

# Frontend logs only
pm2 logs codeframe-frontend-staging

# Log files location
tail -f logs/backend-out.log
tail -f logs/frontend-out.log
```

**Stop Services:**
```bash
pm2 stop all
# OR stop individual
pm2 stop codeframe-backend-staging
pm2 stop codeframe-frontend-staging
```

**Restart Services:**
```bash
pm2 restart all
```

**Delete Processes:**
```bash
pm2 delete all
```

## WSL Persistence Strategy

### Problem
WSL can stop/restart, causing services to shut down. PM2 processes won't auto-start when WSL restarts.

### Solutions

#### Option 1: Manual Restart (Current)
After WSL restarts, manually run:
```bash
cd /home/frankbria/projects/codeframe
./scripts/start-staging.sh
```

#### Option 2: Windows Autostart (For Windows Host)

Automatically start the staging server when Windows boots.

**Prerequisites**: Windows 10/11 with WSL2

**Quick Setup:**
1. Copy PowerShell script to Windows:
   ```powershell
   # In PowerShell (Administrator)
   New-Item -Path "C:\Scripts" -ItemType Directory -Force
   Copy-Item "\\wsl$\Ubuntu\home\frankbria\projects\codeframe\scripts\start-staging-windows.ps1" -Destination "C:\Scripts\start-codeframe-staging.ps1"
   ```

2. Create Windows Scheduled Task (Option A - GUI):
   - Open Task Scheduler (`Win+R` → `taskschd.msc`)
   - Create Basic Task → Name: "CodeFRAME Staging Server"
   - Trigger: "When the computer starts"
   - Action: "Start a program"
   - Program: `powershell.exe`
   - Arguments: `-ExecutionPolicy Bypass -WindowStyle Hidden -File C:\Scripts\start-codeframe-staging.ps1`
   - Run whether user is logged on or not: ✓
   - Run with highest privileges: ✓

3. Create Windows Scheduled Task (Option B - PowerShell):
   ```powershell
   # In PowerShell (Administrator)
   $Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File C:\Scripts\start-codeframe-staging.ps1"
   $Trigger = New-ScheduledTaskTrigger -AtStartup
   $Principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
   $Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

   Register-ScheduledTask -TaskName "CodeFRAME Staging Server" -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings
   ```

**Verify Setup:**
```powershell
# Test manually (without reboot)
Start-ScheduledTask -TaskName "CodeFRAME Staging Server"

# Check log
Get-Content C:\Scripts\codeframe-staging-startup.log -Tail 20

# Verify services
wsl -d Ubuntu -u frankbria bash -c "pm2 list"
```

**Full documentation:** See `scripts/WINDOWS_AUTOSTART_SETUP.md`

#### Option 3: systemd Service (Recommended for WSL with systemd)

**Prerequisites**: WSL2 with systemd enabled

**Check if systemd is available:**
```bash
systemctl --version
```

**Install the systemd service:**
```bash
# Run the installation script
sudo ./scripts/install-systemd-service.sh
```

This will:
- Copy `systemd/codeframe-staging.service` to `/etc/systemd/system/`
- Enable the service to start on WSL boot
- Reload systemd daemon

**Manual installation (if needed):**
```bash
# Copy service file
sudo cp systemd/codeframe-staging.service /etc/systemd/system/
sudo chmod 644 /etc/systemd/system/codeframe-staging.service

# Reload systemd and enable service
sudo systemctl daemon-reload
sudo systemctl enable codeframe-staging.service
sudo systemctl start codeframe-staging.service
```

**Verify service is running:**
```bash
sudo systemctl status codeframe-staging
```

**Service Management:**
```bash
sudo systemctl start codeframe-staging    # Start service
sudo systemctl stop codeframe-staging     # Stop service
sudo systemctl restart codeframe-staging  # Restart service
sudo systemctl disable codeframe-staging  # Disable autostart
sudo journalctl -u codeframe-staging -f   # View logs
```

### Health Monitoring

Automated health checking and auto-recovery for the staging server.

#### Daily Health Checker

The health checker monitors PM2 processes and service ports, automatically restarting if issues are detected.

**What it checks:**
- PM2 process manager is running
- Backend and frontend processes are online
- Port 8000 (backend) is responding
- Port 3000 (frontend) is responding

**Install systemd timer (daily checks at 2 AM + 15 min after boot):**
```bash
# Install health check timer
sudo ./scripts/install-health-check.sh
```

**Manual health check:**
```bash
# Run health check now
./scripts/health-check.sh

# View health check log
tail -f logs/health-check.log
```

**Health check configuration:**
- Runs daily at 2:00 AM
- Runs 15 minutes after system boot
- Auto-restarts services if unhealthy (up to 3 attempts)
- Logs all checks to `logs/health-check.log`

**Management commands:**
```bash
# Trigger health check manually
sudo systemctl start codeframe-health-check.service

# Check timer status
sudo systemctl status codeframe-health-check.timer

# View next scheduled run
systemctl list-timers codeframe-health-check.timer

# Disable health checks
sudo systemctl stop codeframe-health-check.timer
sudo systemctl disable codeframe-health-check.timer

# View health check logs
sudo journalctl -u codeframe-health-check -f
```

**Alternative: Cron-based health check (if not using systemd timer):**
```bash
# Add to crontab
crontab -e

# Add this line for daily 2 AM checks
0 2 * * * /home/frankbria/projects/codeframe/scripts/health-check.sh >> /home/frankbria/projects/codeframe/logs/health-check.log 2>&1
```

## Network Access Setup

### Local Network Access

1. **Get WSL IP Address:**
```bash
ip addr show eth0 | grep 'inet ' | awk '{print $2}' | cut -d/ -f1
```

2. **Windows Firewall Rules:**

Open PowerShell as Administrator and run:
```powershell
# Allow port 3000 (Frontend)
New-NetFirewallRule -DisplayName "CodeFRAME Frontend Staging" -Direction Inbound -LocalPort 3000 -Protocol TCP -Action Allow

# Allow port 8000 (Backend)
New-NetFirewallRule -DisplayName "CodeFRAME Backend Staging" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow
```

3. **Port Forwarding from Windows to WSL (if needed):**

WSL2 uses a virtual network adapter, so ports are usually accessible directly. If not:

```powershell
# Get WSL IP
wsl hostname -I

# Forward ports
netsh interface portproxy add v4tov4 listenport=3000 listenaddress=0.0.0.0 connectport=3000 connectaddress=<WSL_IP>
netsh interface portproxy add v4tov4 listenport=8000 listenaddress=0.0.0.0 connectport=8000 connectaddress=<WSL_IP>

# View port forwarding rules
netsh interface portproxy show all

# Delete port forwarding (if needed)
netsh interface portproxy delete v4tov4 listenport=3000 listenaddress=0.0.0.0
netsh interface portproxy delete v4tov4 listenport=8000 listenaddress=0.0.0.0
```

### Router Configuration

**Option 1: Static IP Assignment**
1. Access router admin panel (usually 192.168.1.1)
2. Find DHCP settings
3. Reserve IP for Windows host MAC address
4. Note the assigned IP (e.g., 192.168.1.100)

**Option 2: Port Forwarding (for external access)**
1. Forward external ports to Windows host IP
2. Frontend: External 3000 → 192.168.1.100:3000
3. Backend: External 8000 → 192.168.1.100:8000

### Tailscale Setup

**Windows Host Tailscale:**
1. Install Tailscale on Windows
2. WSL ports are automatically accessible via Windows Tailscale IP
3. Access from any Tailscale device: http://<tailscale-ip>:3000

**Access URLs:**
- Frontend: http://100.x.x.x:3000 (use your Tailscale IP)
- Backend: http://100.x.x.x:8000

## Testing the Staging Server

### Manual Test Checklist

1. **Service Health:**
```bash
# Check processes
npx pm2 list

# Both should show "online" status
# codeframe-backend-staging
# codeframe-frontend-staging
```

2. **Backend API Test:**
```bash
# Health check
curl http://localhost:8000/health

# List projects
curl http://localhost:8000/api/projects

# API documentation
curl http://localhost:8000/docs
```

3. **Frontend Access:**
- Open browser: http://localhost:3000
- Should see CodeFRAME dashboard
- Should show any existing projects

4. **Database Verification:**
```bash
sqlite3 staging/.codeframe/state.db ".tables"
# Should show: agents, blockers, changelog, checkpoints, context_items, memory, projects, tasks
```

5. **Network Access Test:**
```bash
# From another device on LAN
curl http://<WSL_IP>:8000/health
# Should return: {"status":"ok"}
```

### Sprint 1 Functionality Tests

Follow the manual testing checklist in `TESTING.md`:

1. **Project Creation (cf-8, cf-11)**
   - Create project via API: `curl -X POST http://localhost:8000/api/projects -H "Content-Type: application/json" -d '{"project_name": "test", "project_type": "python"}'`
   - Verify in dashboard

2. **Lead Agent (cf-9)**
   - Test Lead Agent initialization
   - Send test message via API

3. **Agent Lifecycle (cf-10)**
   - Start agent via API
   - Verify WebSocket updates

## Troubleshooting

### PM2 Process Won't Start

**Issue**: `pm2 start` fails
**Solutions**:
```bash
# Check PM2 installation
pm2 --version

# If not found, install globally
sudo npm install -g pm2

# Clear PM2 processes
pm2 delete all
pm2 kill

# Restart with verbose output
pm2 start ecosystem.staging.config.js --log-date-format="YYYY-MM-DD HH:mm:ss"
```

### Port Already in Use

**Issue**: "Address already in use" error
**Solutions**:
```bash
# Find process using port 3000
lsof -i :3000
# OR
ss -tulpn | grep :3000

# Kill process
kill -9 <PID>

# Start PM2 again
pm2 start ecosystem.staging.config.js
```

### WSL Network Issues

**Issue**: Can't access from Windows/LAN
**Solutions**:
```bash
# 1. Check WSL IP
ip addr show eth0

# 2. Test from WSL
curl http://localhost:3000
curl http://localhost:8000

# 3. Test from Windows PowerShell
curl http://localhost:3000
# If this fails, check Windows firewall

# 4. Restart WSL networking
wsl --shutdown
# Then restart WSL
```

### Database Lock Errors

**Issue**: "database is locked"
**Solutions**:
```bash
# Stop all processes
pm2 stop all

# Check for stale locks
ls -la staging/.codeframe/
# Delete .db-shm and .db-wal if present
rm staging/.codeframe/state.db-shm
rm staging/.codeframe/state.db-wal

# Restart services
pm2 start ecosystem.staging.config.js
```

### Logs Not Showing

**Issue**: No log output
**Solutions**:
```bash
# Check log directory
ls -la logs/

# Ensure write permissions
chmod 755 logs/

# Check PM2 log paths
pm2 show codeframe-backend-staging | grep log

# View logs directly
tail -f logs/backend-out.log
tail -f logs/backend-error.log
```

## Maintenance

### Updating the Staging Environment

1. **Pull latest code:**
```bash
cd /home/frankbria/projects/codeframe
git pull origin main
```

2. **Update dependencies:**
```bash
# Python
source venv/bin/activate
pip install -e .

# Frontend
cd web-ui
npm install
cd ..
```

3. **Restart services:**
```bash
pm2 restart all
```

### Monitoring

**Real-time monitoring:**
```bash
pm2 monit
```

**Resource usage:**
```bash
pm2 list
# Shows: CPU %, Memory usage for each process
```

**Log rotation:**
PM2 automatically manages log rotation. Configure in `ecosystem.staging.config.js` if needed.

## Security Considerations

1. **API Key Security:**
   - Never commit `.env.staging` to git
   - Rotate API keys periodically
   - Use environment variables for sensitive data

2. **Network Security:**
   - Staging server should be on trusted network only
   - Use Tailscale for remote access (encrypted)
   - Don't expose staging to public internet

3. **Database Security:**
   - Staging database is isolated from production
   - Regular backups recommended
   - Use separate test data

## Next Steps

### Production Deployment

When moving to production:
1. Use Docker containers for better isolation
2. Set up proper reverse proxy (nginx)
3. Enable HTTPS with Let's Encrypt
4. Use production-grade database (PostgreSQL)
5. Implement proper monitoring (Prometheus/Grafana)
6. Set up automated backups

### Current Limitations

- **WSL Restarts**: Requires manual service restart (mitigated by Windows Task Scheduler)
- **No Load Balancing**: Single instance only
- **Limited Monitoring**: Basic PM2 monitoring only
- **No HTTPS**: HTTP only (add reverse proxy for HTTPS)

## Support

For issues or questions:
1. Check this documentation
2. Review logs: `npx pm2 logs`
3. Check TESTING.md for manual test procedures
4. Review Sprint 1 implementation docs in docs/archive/sprint1/
