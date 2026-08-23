#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

# Kill existing processes on port 8000 (API) and port 5180 (Web)
for port in 8000 5180; do
  pids=$(lsof -ti :$port 2>/dev/null || true)
  if [ -n "$pids" ]; then
    kill $pids 2>/dev/null || true
  fi
done
sleep 1

cleanup() { kill 0 2>/dev/null || true; }
trap cleanup INT TERM EXIT

cd services/api && uv run uvicorn mindweaver.main:app --reload --port 8000 &
npm run web:dev &

echo ""
echo "  API  → http://localhost:8000"
echo "  Web  → http://localhost:5180"
echo ""

wait
