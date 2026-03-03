#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PORT="${PORT:-8000}"

get_lan_ip() {
  ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "127.0.0.1"
}

LAN_IP="$(get_lan_ip)"

if [[ ! -x "$ROOT_DIR/.venv/bin/python" ]]; then
  echo "Creating Python virtual environment..."
  python3 -m venv "$ROOT_DIR/.venv"
fi

echo "Installing backend dependencies (if needed)..."
"$ROOT_DIR/.venv/bin/pip" install -q -r "$ROOT_DIR/requirements.txt"

if [[ ! -d "$ROOT_DIR/web/node_modules" ]]; then
  echo "Installing frontend dependencies..."
  cd "$ROOT_DIR/web"
  npm install
else
  cd "$ROOT_DIR/web"
fi

echo "Building frontend..."
npm run build

cd "$ROOT_DIR"

EXISTING_PID="$(lsof -ti tcp:"$PORT" -sTCP:LISTEN || true)"
if [[ -n "$EXISTING_PID" ]]; then
  echo "Port $PORT is in use (PID: $EXISTING_PID). Restarting it..."
  kill "$EXISTING_PID" || true
  sleep 1
fi

echo ""
echo "Share this URL on the same Wi-Fi:"
echo "  http://$LAN_IP:$PORT"
echo ""
echo "Starting server..."

exec "$ROOT_DIR/.venv/bin/python" -m uvicorn server:app --host 0.0.0.0 --port "$PORT"
