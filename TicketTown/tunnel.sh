#!/usr/bin/env bash
# Puts your local backend on the public internet with a free Cloudflare quick tunnel (no account needed).
#
#   ./tunnel.sh          # tunnels http://localhost:3000
#   ./tunnel.sh 8080     # or another port
#
# Prints an https://<random-words>.trycloudflare.com address. Paste it into the website's ⚙ settings,
# or set it as TICKETTOWN_API_URL for the MCP server. The address changes every time you restart this.
set -e
PORT="${1:-3000}"
CF="$(command -v cloudflared || true)"
[ -z "$CF" ] && [ -x "$HOME/.local/bin/cloudflared" ] && CF="$HOME/.local/bin/cloudflared"
if [ -z "$CF" ]; then
  echo "cloudflared is not installed. Get it from https://github.com/cloudflare/cloudflared/releases"
  exit 1
fi
curl -s -m 3 -o /dev/null "http://localhost:$PORT/api/health" || echo "⚠️  Nothing answers on localhost:$PORT yet. Start the backend first (./start-local.sh)."

LOG="$(mktemp)"
"$CF" tunnel --no-autoupdate --url "http://localhost:$PORT" >"$LOG" 2>&1 &
TUNNEL_PID=$!
trap 'kill $TUNNEL_PID 2>/dev/null; rm -f "$LOG"' EXIT

URL=""
for _ in $(seq 1 30); do
  URL="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG" | head -1 || true)"
  [ -n "$URL" ] && break
  sleep 1
done
[ -z "$URL" ] && { echo "Could not get a tunnel address. Log:"; cat "$LOG"; exit 1; }

# The new name takes a few seconds to appear in DNS. Ask Cloudflare's resolver (1.1.1.1) directly, so
# your own machine doesn't look it up too early and cache a "does not exist" answer.
HOST="${URL#https://}"
for _ in $(seq 1 60); do
  python3 - "$HOST" <<'EOF' && break
import socket, sys
q = b'\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00' + b''.join(bytes([len(p)]) + p.encode() for p in sys.argv[1].split('.')) + b'\x00\x00\x01\x00\x01'
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.settimeout(3)
try:
    s.sendto(q, ('1.1.1.1', 53)); d = s.recv(512)
    sys.exit(0 if (d[3] & 15) == 0 and d[7] > 0 else 1)
except Exception:
    sys.exit(1)
EOF
  sleep 2
done
sleep 3

echo
echo "✅ Your backend is public at:"
echo
echo "     $URL"
echo
echo "   Check it:   curl $URL/api/health"
echo "   Website:    click ⚙ in the header, paste the address, press Test connection"
echo "   MCP:        TICKETTOWN_API_URL=$URL python server.py"
echo
echo "   Leave this window open. Ctrl+C stops the tunnel."
wait $TUNNEL_PID
