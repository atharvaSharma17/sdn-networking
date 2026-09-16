#!/bin/bash

echo "=========================================================="
echo " CarbonRoute: SDN Multi-Objective Routing Simulator"
echo "=========================================================="

mkdir -p data

if [ ! -d "venv" ]; then
    echo "[*] Initializing virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

echo "[*] Checking Python dependencies..."
pip install -q fastapi uvicorn networkx

echo "[*] Launching application server..."
echo ""
echo " Dashboard: http://localhost:8000"
echo " API Docs:  http://localhost:8000/docs"
echo ""
echo " Press Ctrl+C to terminate."
echo "=========================================================="

python3 -m uvicorn src.backend.api:app --host 0.0.0.0 --port 8000
