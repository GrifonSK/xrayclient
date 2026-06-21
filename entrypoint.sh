#!/bin/bash
set -e

mkdir -p /mnt/xrayclient/backups

if [ ! -f /mnt/xrayclient/users.txt ]; then
    echo "# SOCKS5 users (user:pass one per line)" > /mnt/xrayclient/users.txt
    echo "admin:admin" >> /mnt/xrayclient/users.txt
    echo "Created default users.txt with admin:admin"
fi

python3 /mnt/xrayclient/update_xray_config.py --force || echo "Initial config generation skipped (subscriptions may be empty)"

crond

echo "Starting Xray..."
exec /usr/local/bin/xray run -c /mnt/xrayclient/config.json
