#!/bin/bash
set -e

ROOT_DIR="/mnt/xrayclient"
SCRIPTS_DIR="$ROOT_DIR/scripts"
CONFIG_DIR="$ROOT_DIR/config"
XRAY_BIN="/usr/local/bin/xray"

mkdir -p "$CONFIG_DIR/backups"

for f in update_xray_config.py server.py index.html; do
    if [ ! -f "$SCRIPTS_DIR/$f" ] && [ -f "/opt/xrayclient/$f" ]; then
        cp "/opt/xrayclient/$f" "$SCRIPTS_DIR/$f"
        chmod +x "$SCRIPTS_DIR/$f" 2>/dev/null
        echo "Copied $f to scripts directory"
    fi
done

if [ ! -f "$CONFIG_DIR/users.txt" ]; then
    echo "# SOCKS5 users (user:pass one per line)" > "$CONFIG_DIR/users.txt"
    echo "admin:admin" >> "$CONFIG_DIR/users.txt"
    echo "Created default users.txt with admin:admin"
fi

python3 "$SCRIPTS_DIR/update_xray_config.py" --force || echo "Initial config generation skipped (subscriptions may be empty)"

crond

echo "Starting Xray..."
$XRAY_BIN run -c "$CONFIG_DIR/config.json" &
XRAY_PID=$!

echo "Starting Web UI..."
python3 "$SCRIPTS_DIR/server.py" &
WEB_PID=$!

shutdown() {
    echo "Shutting down..."
    kill "$XRAY_PID" "$WEB_PID" 2>/dev/null || true
    wait "$XRAY_PID" "$WEB_PID" 2>/dev/null || true
    exit 0
}
trap shutdown SIGTERM SIGINT

LAST_MTIME=$(stat -c %Y "$CONFIG_DIR/config.json" 2>/dev/null || echo 0)
while true; do
    sleep 10
    NEW_MTIME=$(stat -c %Y "$CONFIG_DIR/config.json" 2>/dev/null || echo 0)
    if [ "$NEW_MTIME" != "$LAST_MTIME" ]; then
        echo "Config changed, restarting Xray..."
        kill "$XRAY_PID" 2>/dev/null || true
        wait "$XRAY_PID" 2>/dev/null || true
        $XRAY_BIN run -c "$CONFIG_DIR/config.json" &
        XRAY_PID=$!
        LAST_MTIME="$NEW_MTIME"
    fi
done
