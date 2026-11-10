#!/usr/bin/env bash
# Install the cloudflared tunnel service for the mini app.
# Usage: install-tunnel.sh <install_dir> <bot_service_name>
# Requires cloudflared (https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/).
set -euo pipefail

INSTALL_DIR="${1:?install dir required}"
SERVICE_NAME="${2:?bot service name required}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v cloudflared >/dev/null; then
    echo "cloudflared not installed - mini app will not be reachable from Telegram." >&2
    exit 0
fi

chmod +x "$HERE/tunnel.sh"

sed -e "s#@INSTALL_DIR@#${INSTALL_DIR}#g" -e "s#@SERVICE_NAME@#${SERVICE_NAME}#g" \
    "$HERE/tunnel.service.template" > "/etc/systemd/system/${SERVICE_NAME}-tunnel.service"

systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}-tunnel"  # no restart: keeps the quick-tunnel URL stable
echo "Tunnel service ${SERVICE_NAME}-tunnel enabled."
