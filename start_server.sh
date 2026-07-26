#!/bin/bash
# ============================================
# Start FB Bot VPS Server + Tunnel
# Run: bash start_server.sh
# ============================================

echo "Locking wake..."
termux-wake-lock

echo "Starting VPS Server..."
cd "$(dirname "$0")"
python3 vps_server.py &
sleep 2

echo "Starting Serveo Tunnel..."
ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=60 -o ServerAliveCountMax=3 -R 80:localhost:5000 serveo.net &
sleep 3

echo ""
echo "========================================="
echo "  SERVER RUNNING!"
echo "========================================="
echo ""
echo "Tunnel URL from logs above (https://xxx.serveousercontent.com)"
echo "Set VPS URL in bot: /setvps <tunnel_url>"
echo "========================================="
