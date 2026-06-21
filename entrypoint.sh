#!/bin/bash
set -e

ROOT_DIR="/mnt/xrayclient"
SCRIPTS_DIR="$ROOT_DIR/scripts"
CONFIG_DIR="$ROOT_DIR/config"

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
exec /usr/local/bin/xray run -c "$CONFIG_DIR/config.json"
