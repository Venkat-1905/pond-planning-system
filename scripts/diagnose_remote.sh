#!/bin/bash
# Diagnostic script for remote stu9_sys1 network & ports

REMOTE_USER="student"
REMOTE_HOST="10.1.75.51"
SSH_PORT="2233"

echo "========================================================================"
echo " Running Network & Port Diagnostics on stu9_sys1..."
echo "========================================================================"

ssh -p ${SSH_PORT} ${REMOTE_USER}@${REMOTE_HOST} "bash -s" << 'REMOTE_SCRIPT'
echo "=== 1. Internal IP Addresses & Network Interfaces ==="
ip -4 a || ifconfig

echo ""
echo "=== 2. Currently Listening TCP Ports on Remote VM ==="
ss -tuln || netstat -tuln

echo ""
echo "=== 3. Testing Local Endpoints on Remote VM ==="
for port in 5233 5000 6233 6000 7233 7000 8000 8080; do
    resp=$(curl -s -m 1 http://localhost:${port}/health 2>/dev/null || echo "Not listening")
    if [ "$resp" != "Not listening" ]; then
        echo " [+] Port ${port}: ACTIVE -> ${resp}"
    fi
done

echo ""
echo "=== 4. Running Python Processes ==="
ps aux | grep -i uvicorn | grep -v grep || echo "No uvicorn process running"
REMOTE_SCRIPT
