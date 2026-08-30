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
REMOTE_DIR="~/pond_system"

echo "========================================================================"
echo " Deploying Village Pond Planning System to ${REMOTE_USER}@${REMOTE_HOST}"
echo " SSH Port: ${REMOTE_SSH_PORT} | Target Web API Port: ${APP_PORT}"
echo "========================================================================"

# 1. Test SSH Connection
echo "[1/4] Checking SSH connection to remote host..."
ssh -p ${REMOTE_SSH_PORT} -o ConnectTimeout=5 ${REMOTE_USER}@${REMOTE_HOST} "mkdir -p ${REMOTE_DIR}" || {
    echo "Failed to connect to ${REMOTE_HOST}:${REMOTE_SSH_PORT}. Please ensure VPN/network connectivity."
    exit 1
}

# 2. Sync Codebase Files
echo "[2/4] Syncing project files to ${REMOTE_DIR}..."
rsync -avz -e "ssh -p ${REMOTE_SSH_PORT}" \
    --exclude ".venv" \
    --exclude "__pycache__" \
    --exclude ".pytest_cache" \
    --exclude ".git" \
    ./ ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/

# 3. Setup Python Environment & Dependencies on Remote VM
echo "[3/4] Setting up remote Python environment & dependencies..."
ssh -p ${REMOTE_SSH_PORT} ${REMOTE_USER}@${REMOTE_HOST} "bash -s" << REMOTE_SCRIPT
cd ${REMOTE_DIR}
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
REMOTE_SCRIPT

# 4. Start Application on Port
echo "[4/4] Starting FastAPI Uvicorn server on port ${APP_PORT}..."
ssh -p ${REMOTE_SSH_PORT} ${REMOTE_USER}@${REMOTE_HOST} "bash -s" << REMOTE_SCRIPT
cd ${REMOTE_DIR}
source .venv/bin/activate

# Kill any existing server running on this port
pkill -f "uvicorn backend.app:app.*--port ${APP_PORT}" || true

# Start server in background with nohup
nohup uvicorn backend.app:app --host 0.0.0.0 --port ${APP_PORT} > server.log 2>&1 &
sleep 2

# Verify process is active
if pgrep -f "uvicorn backend.app:app.*--port ${APP_PORT}" > /dev/null; then
    echo "Server successfully started on port ${APP_PORT}!"
else
    echo "Server failed to start. Last log lines:"
    tail -n 20 server.log
    exit 1
fi
REMOTE_SCRIPT

echo "========================================================================"
echo " Deployment Complete!"
echo " Public / Internal URL: http://${REMOTE_HOST}:${APP_PORT}"
echo " Interactive Swagger UI: http://${REMOTE_HOST}:${APP_PORT}/docs"
echo " Web Dashboard UI:       http://${REMOTE_HOST}:${APP_PORT}/"
echo "========================================================================"
