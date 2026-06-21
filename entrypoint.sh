#!/bin/bash
set -e

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
DATA_DIR="/mnt/xrayclient"

mkdir -p "$DATA_DIR/backups"

for f in update_xray_config.py server.py index.html; do
    if [ ! -f "$DATA_DIR/$f" ] && [ -f "$SCRIPT_DIR/$f" ]; then
        cp "$SCRIPT_DIR/$f" "$DATA_DIR/$f"
        echo "Copied $f to data directory"
    fi
done

if [ ! -f "$DATA_DIR/users.txt" ]; then
    echo "# SOCKS5 users (user:pass one per line)" > "$DATA_DIR/users.txt"
    echo "admin:admin" >> "$DATA_DIR/users.txt"
    echo "Created default users.txt with admin:admin"
fi

python3 "$DATA_DIR/update_xray_config.py" --force || echo "Initial config generation skipped (subscriptions may be empty)"

crond

echo "Starting Xray..."
exec /usr/local/bin/xray run -c "$DATA_DIR/config.json"
