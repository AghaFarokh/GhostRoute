#!/usr/bin/env bash
# Run a cloudflared quick tunnel to the mini app and publish its URL to
# tunnel_url.txt (read by the bot). Used by iraniexchange-tunnel.service.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${MINIAPP_PORT:-18471}"
URL_FILE="$DIR/tunnel_url.txt"

rm -f "$URL_FILE"

cloudflared tunnel --no-autoupdate --url "http://127.0.0.1:${PORT}" 2>&1 | while IFS= read -r line; do
    echo "$line"
    if [[ "$line" =~ (https://[a-z0-9-]+\.trycloudflare\.com) ]]; then
        echo "${BASH_REMATCH[1]}" > "$URL_FILE"
    fi
done
