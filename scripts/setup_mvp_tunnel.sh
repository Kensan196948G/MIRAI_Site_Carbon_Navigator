#!/usr/bin/env bash
# One-time setup for the MVP Cloudflare Tunnel + systemd services.
#
# Creates a named tunnel, routes carbon-mvp.mirai-dx-platform.com to the
# local MVP backend (127.0.0.1:8021), and installs the user systemd units.
#
# Requirements: cloudflared installed and authenticated
# (CLOUDFLARE_API_TOKEN or origin cert in ~/.cloudflared).
set -euo pipefail

TUNNEL_NAME="${TUNNEL_NAME:-mirai-carbon-mvp}"
HOSTNAME="${MVP_HOSTNAME:-carbon-mvp.mirai-dx-platform.com}"
PORT="${MVP_PORT:-8021}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLOUDFLARED="${CLOUDFLARED:-/usr/local/bin/cloudflared}"
CF_DIR="${CLOUDFLARED_HOME:-$HOME/.cloudflared}"
CONFIG="$CF_DIR/mirai-carbon-mvp-config.yml"

mkdir -p "$CF_DIR"

if ! "$CLOUDFLARED" tunnel list | grep -qw "$TUNNEL_NAME"; then
  echo "[setup-mvp] creating tunnel $TUNNEL_NAME"
  "$CLOUDFLARED" tunnel create "$TUNNEL_NAME"
fi

TUNNEL_ID="$("$CLOUDFLARED" tunnel list --output json | python3 -c "
import json, sys
name = '$TUNNEL_NAME'
data = json.load(sys.stdin)
print(next(t['id'] for t in data if t['name'] == name))
")"

# Write the tunnel-specific config BEFORE routing DNS: cloudflared's default
# config may point at another tunnel and would silently route the wrong CNAME.
cat > "$CONFIG" <<EOF
tunnel: $TUNNEL_ID
credentials-file: $CF_DIR/$TUNNEL_ID.json

ingress:
  - hostname: $HOSTNAME
    service: http://127.0.0.1:$PORT
  - service: http_status:404
EOF
chmod 600 "$CONFIG"

echo "[setup-mvp] routing $HOSTNAME -> http://127.0.0.1:$PORT (tunnel $TUNNEL_ID)"
if [ -n "${CLOUDFLARE_API_TOKEN:-}" ]; then
  ZONE_ID="$(curl -fsS -m 15 -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
    "https://api.cloudflare.com/client/v4/zones?name=mirai-dx-platform.com" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"][0]["id"])')"
  RECORD_ID="$(curl -fsS -m 15 -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
    "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records?name=$HOSTNAME" \
    | python3 -c 'import json,sys; r=json.load(sys.stdin)["result"]; print(r[0]["id"] if r else "")')"
  PAYLOAD="{\"type\":\"CNAME\",\"name\":\"$HOSTNAME\",\"content\":\"$TUNNEL_ID.cfargotunnel.com\",\"proxied\":true,\"ttl\":1}"
  if [ -n "$RECORD_ID" ]; then
    curl -fsS -m 15 -X PATCH -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
      -H "Content-Type: application/json" \
      "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records/$RECORD_ID" \
      -d "$PAYLOAD" > /dev/null
  else
    curl -fsS -m 15 -X POST -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
      -H "Content-Type: application/json" \
      "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records" \
      -d "$PAYLOAD" > /dev/null
  fi
else
  "$CLOUDFLARED" --config "$CONFIG" tunnel route dns --overwrite-dns \
    "$TUNNEL_NAME" "$HOSTNAME"
fi

for unit in mirai-carbon-mvp mirai-carbon-mvp-cloudflared; do
  dest="$HOME/.config/systemd/user/$unit.service"
  cp "$ROOT/scripts/$unit.service.example" "$dest"
  chmod 644 "$dest"
done
systemctl --user daemon-reload
systemctl --user enable --now mirai-carbon-mvp.service
systemctl --user enable --now mirai-carbon-mvp-cloudflared.service

echo "[setup-mvp] DONE: https://$HOSTNAME"
