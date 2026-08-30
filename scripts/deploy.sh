#!/bin/bash
# ==============================================================================
# DEPLOYMENT SCRIPT FOR VILLAGE POND PLANNING SYSTEM
# Target Server: stu9_sys1 (10.1.75.51) | SSH Port: 2233
# Web Port: 5233 (or 6233 / 7233)
# ==============================================================================

set -e

REMOTE_USER="student"
REMOTE_HOST="10.1.75.51"
REMOTE_SSH_PORT="${SSH_PORT:-2233}"
APP_PORT="${PORT:-5233}"
REMOTE_DIR="pond_system"

echo "========================================================================"
echo " Deploying Village Pond Planning System to ${REMOTE_USER}@${REMOTE_HOST}"
echo " SSH Port: ${REMOTE_SSH_PORT} | Target Web API Port: ${APP_PORT}"
echo "========================================================================"

# 1. Create Remote Directory
echo "[1/4] Ensuring remote workspace directory exists..."
ssh -p ${REMOTE_SSH_PORT} ${REMOTE_USER}@${REMOTE_HOST} "mkdir -p ${REMOTE_DIR}"

# 2. Sync Codebase Files via tar over SSH
echo "[2/4] Transferring project files via compressed stream..."
tar --exclude=".venv" \
    --exclude="__pycache__" \
    --exclude=".pytest_cache" \
    --exclude=".git" \
    -czf - . | ssh -p ${REMOTE_SSH_PORT} ${REMOTE_USER}@${REMOTE_HOST} "tar -xzf - -C ${REMOTE_DIR}"

# 3. Setup Python Dependencies on Remote VM
echo "[3/4] Installing Python dependencies on remote VM..."
ssh -p ${REMOTE_SSH_PORT} ${REMOTE_USER}@${REMOTE_HOST} "bash -s" << REMOTE_SCRIPT
cd ${REMOTE_DIR}

# Install dependencies using user/break-system-packages flag for Ubuntu 24.04/PEP 668 environments
python3 -m pip install --break-system-packages -r requirements.txt || \
python3 -m pip install --user --break-system-packages -r requirements.txt || \
pip install --break-system-packages -r requirements.txt
REMOTE_SCRIPT

# 4. Start Application on Port
echo "[4/4] Starting FastAPI Uvicorn server on port ${APP_PORT}..."
ssh -p ${REMOTE_SSH_PORT} ${REMOTE_USER}@${REMOTE_HOST} "bash -s" << REMOTE_SCRIPT
cd ${REMOTE_DIR}

# Kill any existing server running on this port
pkill -f "uvicorn.*--port ${APP_PORT}" || true

# Start server in background with nohup
nohup python3 -m uvicorn backend.app:app --host 0.0.0.0 --port ${APP_PORT} > server.log 2>&1 &
sleep 3

# Verify process is active
if pgrep -f "uvicorn.*--port ${APP_PORT}" > /dev/null; then
    echo "Server successfully running on port ${APP_PORT}!"
else
    echo "Server log output:"
    tail -n 25 server.log
    exit 1
fi
REMOTE_SCRIPT

echo "========================================================================"
echo " Deployment Complete!"
echo " Public / Internal URL: http://${REMOTE_HOST}:${APP_PORT}"
echo " Interactive Swagger UI: http://${REMOTE_HOST}:${APP_PORT}/docs"
echo " Web Dashboard UI:       http://${REMOTE_HOST}:${APP_PORT}/"
echo "========================================================================"
