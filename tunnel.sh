#!/data/data/com.termux/files/usr/bin/bash
LOGFILE="/data/data/com.termux/files/home/logs/tunnel.log"
LAST_URL_FILE="/data/data/com.termux/files/home/logs/last_tunnel_url.txt"

echo "$(date): Tunnel starting..." >> "$LOGFILE"

while true; do
    ssh -o StrictHostKeyChecking=no \
        -o ServerAliveInterval=60 \
        -o ServerAliveCountMax=3 \
        -o ExitOnForwardFailure=yes \
        -R 80:127.0.0.1:5000 \
        serveo.net 2>&1 | while read line; do
        echo "$(date): $line" >> "$LOGFILE"
        if echo "$line" | grep -q "Forwarding HTTP traffic from"; then
            URL=$(echo "$line" | grep -oP 'https://[^\s]+')
            echo "$URL" > "$LAST_URL_FILE"
            echo "$(date): TUNNEL URL: $URL" >> "$LOGFILE"
        fi
    done
    echo "$(date): Tunnel died, restarting in 5s..." >> "$LOGFILE"
    sleep 5
done
