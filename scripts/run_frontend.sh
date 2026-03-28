#!/usr/bin/env bash
# Start both frontend dev servers
set -e
cd "$(dirname "$0")/../frontend"

echo "Installing dependencies..."
npm install --silent

echo "Starting admin dashboard on http://localhost:3000 ..."
npm run dev --workspace=admin-dashboard &

echo "Starting driver dashboard on http://localhost:3001 ..."
npm run dev --workspace=driver-dashboard &

echo ""
echo "Admin:  http://localhost:3000"
echo "Driver: http://localhost:3001?sim_id=YOUR_RUN_ID&ev_id=AMB_01"
echo ""
wait
