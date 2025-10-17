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

# Determine project root from script location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Configuration
LOG_FILE="$PROJECT_ROOT/logs/health-check.log"
FRONTEND_PORT=14100
BACKEND_PORT=14200
MAX_RETRIES=3
SERVICE_TIMEOUT=60

# Ensure log directory exists
mkdir -p "$PROJECT_ROOT/logs"

# Function to log messages
log() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] $1" | tee -a "$LOG_FILE"
}

# Function to check if PM2 is running
check_pm2() {
    if pm2 list 2>/dev/null | grep -q "online"; then
        return 0
    else
        return 1
    fi
}

# Function to check if a port is responding with timeout and retry
check_port() {
    local port=$1
    local service=$2
    local timeout=10
    local elapsed=0

    while [ $elapsed -lt $timeout ]; do
        if curl -sf --max-time 2 "http://localhost:$port" >/dev/null 2>&1; then
            log "✓ $service (port $port) is responding"
            return 0
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done

    log "✗ $service (port $port) is NOT responding after ${timeout}s"
    return 1
}

# Function to check PM2 process status
check_pm2_processes() {
    local backend_status=$(pm2 jlist 2>/dev/null | jq -r '.[] | select(.name=="codeframe-staging-backend") | .pm2_env.status' 2>/dev/null || echo "")
    local frontend_status=$(pm2 jlist 2>/dev/null | jq -r '.[] | select(.name=="codeframe-staging-frontend") | .pm2_env.status' 2>/dev/null || echo "")

    if [ "$backend_status" == "online" ] && [ "$frontend_status" == "online" ]; then
        log "✓ PM2 processes are online"
        return 0
    else
        log "✗ PM2 processes are not all online (backend: ${backend_status:-missing}, frontend: ${frontend_status:-missing})"
        return 1
    fi
}

# Function to wait for service to be ready
wait_for_service() {
    local port=$1
    local service_name=$2
    local timeout=$SERVICE_TIMEOUT
    local elapsed=0

    log "Waiting for $service_name (port $port) to be ready..."

    while [ $elapsed -lt $timeout ]; do
        if curl -sf --max-time 2 "http://localhost:$port" >/dev/null 2>&1; then
            log "✓ $service_name is ready"
            return 0
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done

    log "✗ $service_name failed to start within ${timeout}s"
    return 1
}

# Function to restart services
restart_services() {
    log "🔄 Attempting to restart staging server..."

    # Stop existing processes with graceful shutdown
    pm2 stop all 2>/dev/null || true
    sleep 5
    pm2 delete all 2>/dev/null || true
    sleep 2

    # Start services using the startup script if available
    if [ -f "$PROJECT_ROOT/scripts/start-staging.sh" ]; then
        log "Using start-staging.sh for restart..."
        bash "$PROJECT_ROOT/scripts/start-staging.sh" >> "$LOG_FILE" 2>&1
    else
        log "Using PM2 directly for restart..."
        pm2 start "$PROJECT_ROOT/ecosystem.staging.config.js" >> "$LOG_FILE" 2>&1
    fi

    log "✓ Restart command completed"
}

# Main health check logic
main() {
    log "=== Health Check Started ==="

    local needs_restart=false

    # Check 1: PM2 is running
    if ! check_pm2; then
        log "⚠️  PM2 is not running or has no processes"
        needs_restart=true
    fi

    # Check 2: PM2 processes are online
    if [ "$needs_restart" = false ]; then
        if ! check_pm2_processes; then
            log "⚠️  PM2 processes are not in online state"
            needs_restart=true
        fi
    fi

    # Check 3: Backend port is responding
    if [ "$needs_restart" = false ]; then
        if ! check_port "$BACKEND_PORT" "Backend"; then
            log "⚠️  Backend is not responding on port $BACKEND_PORT"
            needs_restart=true
        fi
    fi

    # Check 4: Frontend port is responding
    if [ "$needs_restart" = false ]; then
        if ! check_port "$FRONTEND_PORT" "Frontend"; then
            log "⚠️  Frontend is not responding on port $FRONTEND_PORT"
            needs_restart=true
        fi
    fi

    # Restart if needed
    if [ "$needs_restart" = true ]; then
        log "🚨 Health check failed - restart required"

        for i in $(seq 1 $MAX_RETRIES); do
            log "Restart attempt $i of $MAX_RETRIES..."
            restart_services

            # Wait for services to be ready
            if wait_for_service "$BACKEND_PORT" "Backend" && wait_for_service "$FRONTEND_PORT" "Frontend"; then
                # Verify PM2 processes are also healthy
                if check_pm2_processes; then
                    log "✅ Health check passed after restart"
                    log "=== Health Check Completed Successfully ==="
                    exit 0
                else
                    log "⚠️  PM2 processes not healthy after restart"
                fi
            else
                log "⚠️  Restart attempt $i failed, services not ready"
            fi

            # Wait before next retry
            if [ $i -lt $MAX_RETRIES ]; then
                log "Waiting 10 seconds before retry..."
                sleep 10
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
