#!/data/data/com.termux/files/usr/bin/bash
# Combined runner: VPS Server + Telegram Bot on same machine
# No tunnel needed — bot connects to localhost:5000 directly

export BOT_DIR="/data/data/com.termux/files/home/fb-page-bot"
export LOG_DIR="/data/data/com.termux/files/home/logs"
mkdir -p "$LOG_DIR"

VPS_PID=""
BOT_PID=""

cleanup() {
    echo "$(date): Shutting down..." >> "$LOG_DIR/combined.log"
    [ -n "$BOT_PID" ] && kill $BOT_PID 2>/dev/null
    [ -n "$VPS_PID" ] && kill $VPS_PID 2>/dev/null
    wait 2>/dev/null
    exit 0
}
trap cleanup SIGTERM SIGINT

kill_all() {
    pkill -9 -f "vps_server.py" 2>/dev/null
    pkill -9 -f "python3 bot.py" 2>/dev/null
    VPS_PID=""
    BOT_PID=""
    sleep 2
}

start_vps() {
    kill -9 $VPS_PID 2>/dev/null 2>&1
    kill -9 $BOT_PID 2>/dev/null 2>&1
    sleep 1
    
    cd "$BOT_DIR"
    python3 vps_server.py >> "$LOG_DIR/vps_server.log" 2>&1 &
    VPS_PID=$!
    
    for i in $(seq 1 20); do
        if curl -s http://127.0.0.1:5000/health > /dev/null 2>&1; then
            echo "$(date): VPS Server ready PID=$VPS_PID" >> "$LOG_DIR/combined.log"
            return 0
        fi
        sleep 1
    done
    echo "$(date): VPS Server failed to start!" >> "$LOG_DIR/combined.log"
    return 1
}

start_bot() {
    kill -9 $BOT_PID 2>/dev/null 2>&1
    sleep 1
    
    cd "$BOT_DIR"
    python3 bot.py >> "$LOG_DIR/bot.log" 2>&1 &
    BOT_PID=$!
    echo "$(date): Bot started PID=$BOT_PID" >> "$LOG_DIR/combined.log"
}

echo "$(date): Starting combined runner..." >> "$LOG_DIR/combined.log"

# Kill ALL old instances first
kill_all

# Set VPS URL to localhost
python3 -c "
import json, os
cfg = os.path.join('$BOT_DIR', 'bot_config.json')
if os.path.exists(cfg):
    with open(cfg) as f: c = json.load(f)
    c['vps_url'] = 'http://127.0.0.1:5000'
    with open(cfg, 'w') as f: json.dump(c, f, indent=4)
    print('VPS URL set to localhost:5000')
" 2>&1 | tee -a "$LOG_DIR/combined.log"

# Start VPS
start_vps || exit 1

# Start Bot
start_bot

# Monitor both processes
while true; do
    sleep 15
    
    if ! kill -0 $VPS_PID 2>/dev/null; then
        echo "$(date): VPS died, restarting both..." >> "$LOG_DIR/combined.log"
        start_vps
        start_bot
        continue
    fi
    
    if ! kill -0 $BOT_PID 2>/dev/null; then
        echo "$(date): Bot died, restarting..." >> "$LOG_DIR/combined.log"
        start_bot
    fi
done
