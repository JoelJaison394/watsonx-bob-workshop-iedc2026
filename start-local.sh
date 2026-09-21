#!/usr/bin/env bash
# Runs everything you need on your laptop:
#   backend  -> http://localhost:3000
#   frontend -> http://localhost:5173
set -e
cd "$(dirname "$0")"

# Use nvm's Node 22 if it's installed (harmless otherwise).
export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh" && nvm use 22 >/dev/null 2>&1 || true
command -v node >/dev/null || { echo "Node.js 22.13+ is required (https://nodejs.org)."; exit 1; }

[ -d backend/node_modules ] || (cd backend && npm install)

trap 'kill 0' EXIT
(cd backend && node src/server.js) &
(cd frontend && python3 -m http.server 5173) &
echo "Open http://localhost:5173  (Ctrl+C to stop both). Put TMDB_API_KEY in backend/.env for real movies."
wait
