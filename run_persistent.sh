#!/bin/bash
# Persistent VPS Server - runs with nohup
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$HOME/logs"
mkdir -p "$LOG_DIR"

# Kill old instances
pkill -f "python3 vps_server.py" 2>/dev/null
sleep 1

# Start server
cd "$SCRIPT_DIR"
nohup python3 vps_server.py > "$LOG_DIR/vps_server.log" 2>&1 &
echo $! > "$LOG_DIR/vps_server.pid"
echo "VPS Server started! PID: $(cat $LOG_DIR/vps_server.pid)"
echo "Log: $LOG_DIR/vps_server.log"
echo "Health: $(curl -s http://127.0.0.1:5000/health 2>/dev/null || echo 'waiting...')"
