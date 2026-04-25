#!/usr/bin/env bash
# Start the backend server
set -e
cd "$(dirname "$0")/.."
echo "Starting backend on http://localhost:8000 ..."
python3 -m uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
