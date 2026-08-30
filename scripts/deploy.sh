#!/bin/bash
# ==============================================================================
# DEPLOYMENT SCRIPT FOR VILLAGE POND PLANNING SYSTEM
# Target Server: stu9_sys1 (10.1.75.51) | SSH Port: 2233
# External Host Ports: 5233, 6233, 7233 -> Container Internal Ports: 5000, 6000, 7000
# ==============================================================================

set -e

REMOTE_USER="student"
REMOTE_HOST="10.1.75.51"
REMOTE_SSH_PORT="${SSH_PORT:-2233}"
REMOTE_DIR="pond_system"

echo "========================================================================"
echo " Deploying Village Pond Planning System to ${REMOTE_USER}@${REMOTE_HOST}"
echo " SSH Port: ${REMOTE_SSH_PORT}"
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

# 3. Setup Python Dependencies & Launch Server on Remote VM
echo "[3/4] Installing dependencies & launching server on remote VM..."
ssh -p ${REMOTE_SSH_PORT} ${REMOTE_USER}@${REMOTE_HOST} "bash -s" << 'REMOTE_SCRIPT'
cd pond_system

echo "Installing Python dependencies with pip..."
python3 -m pip install --break-system-packages -r requirements.txt || \
python3 -m pip install --user --break-system-packages -r requirements.txt || \
pip install --break-system-packages -r requirements.txt

echo "Stopping any previous instances..."
pkill -f "uvicorn.*backend.app:app" || true
sleep 1

echo "Starting Uvicorn servers on internal ports (5000, 6000, 7000, 5233)..."
# Start on port 5000 (mapped to external 5233)
nohup python3 -m uvicorn backend.app:app --host 0.0.0.0 --port 5000 > server_5000.log 2>&1 &
# Start on port 6000 (mapped to external 6233)
nohup python3 -m uvicorn backend.app:app --host 0.0.0.0 --port 6000 > server_6000.log 2>&1 &
# Start on port 7000 (mapped to external 7233)
nohup python3 -m uvicorn backend.app:app --host 0.0.0.0 --port 7000 > server_7000.log 2>&1 &
# Start directly on port 5233 as well in case direct mapping is used
nohup python3 -m uvicorn backend.app:app --host 0.0.0.0 --port 5233 > server_5233.log 2>&1 &

sleep 3

echo "--- Active Ports Check ---"
for p in 5000 6000 7000 5233; do
    res=$(curl -s http://localhost:${p}/health || echo "FAILED")
    echo "Port ${p}: ${res}"
done
REMOTE_SCRIPT

echo "========================================================================"
echo " [4/4] Deployment Verified!"
echo " Primary External URLs to open in browser:"
echo "   - http://${REMOTE_HOST}:5233/ (Web Dashboard UI)"
echo "   - http://${REMOTE_HOST}:5233/docs (Interactive Swagger UI)"
echo "   - http://${REMOTE_HOST}:6233/ (Alternative Port)"
echo "   - http://${REMOTE_HOST}:7233/ (Alternative Port)"
echo "========================================================================"
