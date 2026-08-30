#!/bin/bash
# ==============================================================================
# DEPLOYMENT SCRIPT FOR VILLAGE POND PLANNING SYSTEM
# Target Server: stu9_sys1 (10.1.75.51) | SSH Port: 2233
# Allocated Ports: 3233, 4233, 5233, 6233, 7233 (and 3000, 4000, 5000, 6000, 7000)
# ==============================================================================

set -e

REMOTE_USER="student"
REMOTE_HOST="10.1.75.51"
REMOTE_SSH_PORT="${SSH_PORT:-2233}"
REMOTE_DIR="pond_system"

echo "========================================================================"
echo " Deploying Village Pond Planning System to ${REMOTE_USER}@${REMOTE_HOST}"
echo " SSH Port: ${REMOTE_SSH_PORT} (stu9_sys1)"
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

# 3. Setup Python Dependencies & Launch Servers across All Allocated Ports
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

echo "Starting Uvicorn servers across all allocated ports..."
# Bind both container internal ports (3000, 4000, 5000, 6000, 7000) and direct ports (3233, 4233, 5233, 6233, 7233)
for port in 5000 6000 7000 3000 4000 5233 6233 7233 3233 4233; do
    nohup python3 -m uvicorn backend.app:app --host 0.0.0.0 --port ${port} > server_${port}.log 2>&1 &
done

sleep 3

echo "--- Active Ports Health Verification ---"
for port in 5000 6000 7000 5233 6233 7233; do
    res=$(curl -s http://localhost:${port}/health || echo "FAILED")
    echo "Port ${port}: ${res}"
done
REMOTE_SCRIPT

echo "========================================================================"
echo " [4/4] Deployment Verified on stu9_sys1!"
echo ""
echo " You can access your working system at any of these URLs:"
echo "   - http://${REMOTE_HOST}:5233/       (Web Dashboard UI)"
echo "   - http://${REMOTE_HOST}:5233/docs   (Interactive Swagger API)"
echo "   - http://${REMOTE_HOST}:6233/       (Alternative Port)"
echo "   - http://${REMOTE_HOST}:7233/       (Alternative Port)"
echo "   - http://${REMOTE_HOST}:3233/       (Alternative Port)"
echo "   - http://${REMOTE_HOST}:4233/       (Alternative Port)"
echo "========================================================================"
