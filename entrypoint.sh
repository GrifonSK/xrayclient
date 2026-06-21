#!/bin/bash
set -e

mkdir -p /mnt/xrayclient/backups

python3 /mnt/xrayclient/update_xray_config.py --force || echo "Initial config generation skipped (subscriptions may be empty)"

crond

echo "Starting Xray..."
exec /usr/local/bin/xray run -c /mnt/xrayclient/config.json
