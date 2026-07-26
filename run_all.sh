#!/data/data/com.termux/files/usr/bin/bash
# Combined runner: VPS Server + Telegram Bot on same machine
# No tunnel needed — bot connects to localhost:5000 directly

export BOT_DIR="/data/data/com.termux/files/home/fb-page-bot"
export LOG_DIR="/data/data/com.termux/files/home/logs"
mkdir -p "$LOG_DIR"

cleanup() {
    echo "$(date): Shutting down..." >> "$LOG_DIR/combined.log"
    kill $VPS_PID $BOT_PID 2>/dev/null
    wait $VPS_PID $BOT_PID 2>/dev/null
    exit 0
}
trap cleanup SIGTERM SIGINT

# Kill old processes
pkill -f "vps_server.py" 2>/dev/null
pkill -f "bot.py" 2>/dev/null
sleep 2

echo "$(date): Starting combined runner..." >> "$LOG_DIR/combined.log"

# Start VPS Server
cd "$BOT_DIR"
python3 vps_server.py >> "$LOG_DIR/vps_server.log" 2>&1 &
VPS_PID=$!
echo "$(date): VPS Server started PID=$VPS_PID" >> "$LOG_DIR/combined.log"

# Wait for VPS to be ready
for i in $(seq 1 20); do
    if curl -s http://127.0.0.1:5000/health > /dev/null 2>&1; then
        echo "$(date): VPS Server ready" >> "$LOG_DIR/combined.log"
        break
    fi
    sleep 1
done

# Set VPS URL to localhost
if [ -f "$BOT_DIR/bot_config.json" ]; then
    python3 -c "
import json
with open('$BOT_DIR/bot_config.json') as f: c = json.load(f)
c['vps_url'] = 'http://127.0.0.1:5000'
with open('$BOT_DIR/bot_config.json','w') as f: json.dump(c,f,indent=4)
print('VPS URL set to localhost:5000')
" 2>&1 | tee -a "$LOG_DIR/combined.log"
fi

# Start Telegram Bot
python3 bot.py >> "$LOG_DIR/bot.log" 2>&1 &
BOT_PID=$!
echo "$(date): Bot started PID=$BOT_PID" >> "$LOG_DIR/combined.log"

# Monitor both processes
while true; do
    if ! kill -0 $VPS_PID 2>/dev/null; then
        echo "$(date): VPS died, restarting..." >> "$LOG_DIR/combined.log"
        cd "$BOT_DIR"
        python3 vps_server.py >> "$LOG_DIR/vps_server.log" 2>&1 &
        VPS_PID=$!
    fi
    if ! kill -0 $BOT_PID 2>/dev/null; then
        echo "$(date): Bot died, restarting..." >> "$LOG_DIR/combined.log"
        cd "$BOT_DIR"
        python3 bot.py >> "$LOG_DIR/bot.log" 2>&1 &
        BOT_PID=$!
    fi
    sleep 30
done
