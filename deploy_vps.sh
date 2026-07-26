#!/bin/bash
# ============================================
# VPS Setup - Install Chrome & Deploy Server
# Usage: bash deploy_vps.sh
# ============================================

set -e

echo "========================================="
echo "  FB Bot VPS Server Setup"
echo "========================================/"

# Update system
echo "[1/6] Updating system..."
apt update && apt upgrade -y

# Install Python, pip, Chrome, ChromeDriver
echo "[2/6] Installing Python & Chrome..."
apt install -y python3 python3-pip python3-venv chromium chromium-driver docker.io git curl

# Create bot directory
echo "[3/6] Creating bot directory..."
mkdir -p /opt/fb-bot-server
cd /opt/fb-bot-server

# Copy files
echo "[4/6] Copying server files..."
cp /data/data/com.termux/files/home/fb-page-bot/vps_server.py . 2>/dev/null || true
cp /data/data/com.termux/files/home/fb-page-bot/requirements.txt . 2>/dev/null || true

# Setup Python venv
echo "[5/6] Setting up Python environment..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install flask selenium requests

# Get paths
CHROMEDRIVER_PATH=$(which chromedriver)
CHROMIUM_PATH=$(which chromium)
echo "ChromeDriver: $CHROMEDRIVER_PATH"
echo "Chromium: $CHROMIUM_PATH"

# Create systemd service
echo "[6/6] Creating systemd service..."
cat > /etc/systemd/system/fb-bot-server.service << EOF
[Unit]
Description=FB Bot VPS Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/fb-bot-server
ExecStart=/opt/fb-bot-server/venv/bin/python /opt/fb-bot-server/vps_server.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1
Environment=PORT=5000

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable fb-bot-server
systemctl start fb-bot-server

echo ""
echo "========================================="
echo "  VPS SERVER DEPLOYED!"
echo "========================================="
echo ""
echo "Server IP: $(curl -s ifconfig.me)"
echo "Port: 5000"
echo ""
echo "Test: curl http://$(curl -s ifconfig.me):5000/health"
echo ""
echo "Commands:"
echo "  Status: systemctl status fb-bot-server"
echo "  Logs:   journalctl -u fb-bot-server -f"
echo "  Restart: systemctl restart fb-bot-server"
echo "  Stop:   systemctl stop fb-bot-server"
echo "========================================="
