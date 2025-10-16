#!/usr/bin/env bash
# CodeFRAME Staging Server Health Check Script
# Checks if staging server is running and restarts if needed
# Can be run manually or scheduled via cron/systemd timer

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
PROJECT_ROOT="/home/frankbria/projects/codeframe"
LOG_FILE="$PROJECT_ROOT/logs/health-check.log"
FRONTEND_PORT=3000
BACKEND_PORT=8000
MAX_RETRIES=3
RETRY_DELAY=10

# Ensure log directory exists
mkdir -p "$PROJECT_ROOT/logs"

# Function to log messages
log() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] $1" | tee -a "$LOG_FILE"
}

# Function to check if PM2 is running
check_pm2() {
    cd "$PROJECT_ROOT"
    if npx pm2 list 2>/dev/null | grep -q "online"; then
        return 0
    else
        return 1
    fi
}

# Function to check if a port is responding
check_port() {
    local port=$1
    local service=$2

    if curl -sf "http://localhost:$port" >/dev/null 2>&1; then
        log "✓ $service (port $port) is responding"
        return 0
    else
        log "✗ $service (port $port) is NOT responding"
        return 1
    fi
}

# Function to check PM2 process status
check_pm2_processes() {
    cd "$PROJECT_ROOT"
    local backend_status=$(npx pm2 jlist 2>/dev/null | grep -o '"name":"codeframe-backend-staging","pm2_env":{"status":"[^"]*"' | grep -o 'online')
    local frontend_status=$(npx pm2 jlist 2>/dev/null | grep -o '"name":"codeframe-frontend-staging","pm2_env":{"status":"[^"]*"' | grep -o 'online')

    if [ "$backend_status" == "online" ] && [ "$frontend_status" == "online" ]; then
        log "✓ PM2 processes are online"
        return 0
    else
        log "✗ PM2 processes are not all online (backend: $backend_status, frontend: $frontend_status)"
        return 1
    fi
}

# Function to restart services
restart_services() {
    log "🔄 Attempting to restart staging server..."

    cd "$PROJECT_ROOT"

    # Stop existing processes
    npx pm2 stop all 2>/dev/null || true
    npx pm2 delete all 2>/dev/null || true

    # Wait a moment
    sleep 5

    # Start services using the startup script
    if [ -f "$PROJECT_ROOT/scripts/start-staging.sh" ]; then
        bash "$PROJECT_ROOT/scripts/start-staging.sh" >> "$LOG_FILE" 2>&1
    else
        npx pm2 start ecosystem.staging.config.js >> "$LOG_FILE" 2>&1
    fi

    # Wait for services to start
    sleep 10

    log "✓ Restart completed"
}

# Main health check logic
main() {
    log "=== Health Check Started ==="

    local needs_restart=false

    # Check 1: PM2 is running
    if ! check_pm2; then
        log "⚠️ PM2 is not running or has no processes"
        needs_restart=true
    fi

    # Check 2: PM2 processes are online
    if [ "$needs_restart" = false ]; then
        if ! check_pm2_processes; then
            log "⚠️ PM2 processes are not in online state"
            needs_restart=true
        fi
    fi

    # Check 3: Backend port is responding
    if [ "$needs_restart" = false ]; then
        if ! check_port "$BACKEND_PORT" "Backend"; then
            log "⚠️ Backend is not responding on port $BACKEND_PORT"
            needs_restart=true
        fi
    fi

    # Check 4: Frontend port is responding
    if [ "$needs_restart" = false ]; then
        if ! check_port "$FRONTEND_PORT" "Frontend"; then
            log "⚠️ Frontend is not responding on port $FRONTEND_PORT"
            needs_restart=true
        fi
    fi

    # Restart if needed
    if [ "$needs_restart" = true ]; then
        log "🚨 Health check failed - restart required"

        for i in $(seq 1 $MAX_RETRIES); do
            log "Restart attempt $i of $MAX_RETRIES..."
            restart_services

            sleep $RETRY_DELAY

            # Verify restart was successful
            if check_pm2_processes && check_port "$BACKEND_PORT" "Backend" && check_port "$FRONTEND_PORT" "Frontend"; then
                log "✅ Health check passed after restart"
                log "=== Health Check Completed Successfully ==="
                exit 0
            else
                log "⚠️ Restart attempt $i failed, services still not healthy"
            fi
        done

        log "❌ Failed to restore services after $MAX_RETRIES attempts"
        log "=== Health Check Failed ==="
        exit 1
    else
        log "✅ All health checks passed - services are healthy"
        log "=== Health Check Completed Successfully ==="
        exit 0
    fi
}

# Run main function
main
