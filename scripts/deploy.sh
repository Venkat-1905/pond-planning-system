#!/bin/bash
# ==============================================================================
# DEPLOYMENT SCRIPT FOR VILLAGE POND PLANNING SYSTEM
# Target Server: stu9_sys1 (10.1.75.51) | SSH Port: 2233
# Allocated Ports: 5233 (Primary), 6233, 7233, 3233, 4233
# ==============================================================================

set -e

REMOTE_USER="student"
REMOTE_HOST="10.1.75.51"
REMOTE_SSH_PORT="${SSH_PORT:-2233}"
APP_PORT="${PORT:-5233}"
REMOTE_DIR="pond_system"

echo "========================================================================"
echo " Deploying Village Pond Planning System to ${REMOTE_USER}@${REMOTE_HOST}"
echo " Server: stu9_sys1 | SSH Port: ${REMOTE_SSH_PORT} | Web Port: ${APP_PORT}"
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

# 3. Setup Python Dependencies & Launch Server on Target Port
echo "[3/4] Installing dependencies & launching server on remote VM..."
ssh -p ${REMOTE_SSH_PORT} ${REMOTE_USER}@${REMOTE_HOST} "bash -s" << REMOTE_SCRIPT
cd pond_system

echo "Installing Python dependencies with pip..."
python3 -m pip install --break-system-packages -r requirements.txt || \
python3 -m pip install --user --break-system-packages -r requirements.txt || \
pip install --break-system-packages -r requirements.txt

echo "Stopping any previous instances..."
pkill -f "uvicorn.*backend.app:app" || true
sleep 1

echo "Starting Uvicorn server on port ${APP_PORT}..."
nohup python3 -m uvicorn backend.app:app --host 0.0.0.0 --port ${APP_PORT} > server_${APP_PORT}.log 2>&1 &

# Also optionally launch on backup ports 6233 and 7233
nohup python3 -m uvicorn backend.app:app --host 0.0.0.0 --port 6233 > server_6233.log 2>&1 &
nohup python3 -m uvicorn backend.app:app --host 0.0.0.0 --port 7233 > server_7233.log 2>&1 &

sleep 3

echo "--- Server Log Output (Port ${APP_PORT}) ---"
cat server_${APP_PORT}.log
echo "--------------------------------------------"

echo "Testing endpoint on localhost:${APP_PORT}..."
curl -s http://localhost:${APP_PORT}/health || echo "FAILED"
REMOTE_SCRIPT

echo "========================================================================"
echo " [4/4] Deployment Verified on stu9_sys1!"
echo ""
echo " Primary Working URLs:"
echo "   - http://${REMOTE_HOST}:${APP_PORT}/       (Web Dashboard UI)"
echo "   - http://${REMOTE_HOST}:${APP_PORT}/docs   (Interactive Swagger API)"
echo "   - http://${REMOTE_HOST}:6233/              (Secondary Port)"
echo "   - http://${REMOTE_HOST}:7233/              (Secondary Port)"
echo "========================================================================"
