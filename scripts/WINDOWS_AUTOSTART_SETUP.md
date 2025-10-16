# Windows Autostart Setup Guide

This guide explains how to configure the CodeFRAME staging server to automatically start when Windows boots.

## Prerequisites

- Windows 10/11 with WSL2
- Administrator access to Windows
- CodeFRAME project at `/home/frankbria/projects/codeframe` in WSL

## Setup Steps

### 1. Copy PowerShell Script to Windows

Copy the PowerShell script from WSL to Windows:

```powershell
# In PowerShell (run as Administrator)
New-Item -Path "C:\Scripts" -ItemType Directory -Force
Copy-Item "\\wsl$\Ubuntu\home\frankbria\projects\codeframe\scripts\start-staging-windows.ps1" -Destination "C:\Scripts\start-codeframe-staging.ps1"
```

Alternatively, manually copy the file:
- Source: `\\wsl$\Ubuntu\home\frankbria\projects\codeframe\scripts\start-staging-windows.ps1`
- Destination: `C:\Scripts\start-codeframe-staging.ps1`

### 2. Create Windows Scheduled Task

#### Option A: Using Task Scheduler GUI

1. **Open Task Scheduler**
   - Press `Win + R`
   - Type `taskschd.msc` and press Enter

2. **Create Basic Task**
   - Click "Create Basic Task..." in the right panel
   - Name: `CodeFRAME Staging Server`
   - Description: `Automatically start CodeFRAME staging server in WSL on boot`
   - Click "Next"

3. **Set Trigger**
   - Select "When the computer starts"
   - Click "Next"

4. **Set Action**
   - Select "Start a program"
   - Click "Next"

5. **Configure Program**
   - Program/script: `powershell.exe`
   - Add arguments: `-ExecutionPolicy Bypass -WindowStyle Hidden -File C:\Scripts\start-codeframe-staging.ps1`
   - Click "Next"

6. **Finish Setup**
   - Check "Open the Properties dialog for this task when I click Finish"
   - Click "Finish"

7. **Configure Additional Settings** (in Properties dialog)
   - General tab:
     - ✓ Run whether user is logged on or not
     - ✓ Run with highest privileges
   - Conditions tab:
     - ✓ Start only if the computer is on AC power (uncheck if using laptop)
   - Settings tab:
     - ✓ Allow task to be run on demand
     - ✓ If the task fails, restart every: 1 minute (attempt 3 times)
   - Click "OK"

8. **Enter Windows Password**
   - You'll be prompted for your Windows password to save the task

#### Option B: Using PowerShell (Automated)

Run this PowerShell script as Administrator:

```powershell
# Create the scheduled task
$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File C:\Scripts\start-codeframe-staging.ps1"
$Trigger = New-ScheduledTaskTrigger -AtStartup
$Principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask -TaskName "CodeFRAME Staging Server" -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Description "Automatically start CodeFRAME staging server in WSL on boot"
```

### 3. Test the Setup

#### Manual Test (without rebooting)

```powershell
# In PowerShell (as Administrator)
Start-ScheduledTask -TaskName "CodeFRAME Staging Server"

# Check the log file
Get-Content C:\Scripts\codeframe-staging-startup.log -Tail 20

# Verify services are running in WSL
wsl -d Ubuntu -u frankbria bash -c "cd /home/frankbria/projects/codeframe && npx pm2 list"
```

#### Full Reboot Test

1. Restart Windows
2. Wait 1-2 minutes for startup
3. Check services:
   ```powershell
   wsl -d Ubuntu -u frankbria bash -c "npx pm2 list"
   ```
4. Access the application:
   - Frontend: http://localhost:3000
   - Backend: http://localhost:8000

### 4. Verify Autostart is Working

Check the log file for any errors:

```powershell
Get-Content C:\Scripts\codeframe-staging-startup.log
```

Expected log entries:
```
2024-XX-XX HH:MM:SS - === CodeFRAME Staging Server Startup ===
2024-XX-XX HH:MM:SS - Waiting 30 seconds for WSL to initialize...
2024-XX-XX HH:MM:SS - WSL Status: ...
2024-XX-XX HH:MM:SS - Starting CodeFRAME staging server...
2024-XX-XX HH:MM:SS - ✓ Staging server started successfully
2024-XX-XX HH:MM:SS - === Startup Complete ===
```

## Troubleshooting

### Task doesn't run on boot

1. **Check Task Scheduler**
   - Open Task Scheduler
   - Find "CodeFRAME Staging Server" task
   - Right-click → Properties
   - Verify "Run whether user is logged on or not" is checked
   - Verify "Run with highest privileges" is checked

2. **Check WSL is starting**
   ```powershell
   wsl -l -v
   ```
   If WSL isn't running, you may need to configure WSL to start automatically.

3. **Check log file**
   ```powershell
   Get-Content C:\Scripts\codeframe-staging-startup.log
   ```

### Services not starting

1. **Verify .env.staging exists**
   ```bash
   # In WSL
   ls -la /home/frankbria/projects/codeframe/.env.staging
   ```

2. **Check PM2 installation**
   ```bash
   # In WSL
   cd /home/frankbria/projects/codeframe
   npx pm2 --version
   ```

3. **Manual start test**
   ```bash
   # In WSL
   cd /home/frankbria/projects/codeframe
   ./scripts/start-staging.sh
   ```

### Permission denied errors

1. **Check script execution policy**
   ```powershell
   Get-ExecutionPolicy
   ```
   If it's "Restricted", the task arguments include `-ExecutionPolicy Bypass` to override.

2. **Verify script location**
   ```powershell
   Test-Path C:\Scripts\start-codeframe-staging.ps1
   ```

## Management Commands

### Disable Autostart

```powershell
Disable-ScheduledTask -TaskName "CodeFRAME Staging Server"
```

### Enable Autostart

```powershell
Enable-ScheduledTask -TaskName "CodeFRAME Staging Server"
```

### Remove Autostart

```powershell
Unregister-ScheduledTask -TaskName "CodeFRAME Staging Server" -Confirm:$false
```

### View Task Status

```powershell
Get-ScheduledTask -TaskName "CodeFRAME Staging Server" | Select-Object TaskName, State, LastRunTime, NextRunTime
```

## Alternative: WSL systemd Autostart

If you prefer using WSL's systemd instead of Windows Task Scheduler, see the systemd setup guide in `/home/frankbria/projects/codeframe/scripts/install-systemd-service.sh`.

Note: WSL systemd services start when WSL starts, not when Windows boots. You may still need the Windows Task Scheduler to ensure WSL starts on boot.
