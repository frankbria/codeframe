# CodeFRAME Staging Server - Windows Autostart Script
# This script starts the staging server in WSL when Windows boots
#
# Installation Instructions:
# 1. Copy this file to: C:\Scripts\start-codeframe-staging.ps1
# 2. Open Task Scheduler (taskschd.msc)
# 3. Create Basic Task:
#    - Name: "CodeFRAME Staging Server"
#    - Trigger: "When the computer starts"
#    - Action: "Start a program"
#    - Program: powershell.exe
#    - Arguments: -ExecutionPolicy Bypass -WindowStyle Hidden -File C:\Scripts\start-codeframe-staging.ps1
#    - Run whether user is logged on or not: Yes
#    - Run with highest privileges: Yes

# Log file for troubleshooting
$LogFile = "C:\Scripts\codeframe-staging-startup.log"

# Function to write log messages
function Write-Log {
    param($Message)
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$Timestamp - $Message" | Out-File -FilePath $LogFile -Append
}

Write-Log "=== CodeFRAME Staging Server Startup ==="

# Wait for WSL to be ready (give Windows 30 seconds after boot)
Write-Log "Waiting 30 seconds for WSL to initialize..."
Start-Sleep -Seconds 30

# Check if WSL is available
try {
    $WslCheck = wsl -l -v 2>&1
    Write-Log "WSL Status: $WslCheck"
} catch {
    Write-Log "ERROR: WSL not available - $_"
    exit 1
}

# Start the staging server in WSL
Write-Log "Starting CodeFRAME staging server..."
try {
    # Run the startup script in WSL as user frankbria
    $Result = wsl -d Ubuntu -u frankbria bash -c "cd /home/frankbria/projects/codeframe && ./scripts/start-staging.sh" 2>&1
    Write-Log "Startup script result: $Result"

    # Verify services are running
    Start-Sleep -Seconds 10
    $PmStatus = wsl -d Ubuntu -u frankbria bash -c "cd /home/frankbria/projects/codeframe && npx pm2 list" 2>&1
    Write-Log "PM2 Status: $PmStatus"

    Write-Log "✓ Staging server started successfully"
} catch {
    Write-Log "ERROR: Failed to start staging server - $_"
    exit 1
}

Write-Log "=== Startup Complete ==="
