#!/bin/bash
# Starts the KB Ingestor Admin Dashboard
# Backend serves both the API and the frontend SPA at http://localhost:8000
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Installing backend dependencies..."
pip install fastapi uvicorn "python-jose[cryptography]" bcrypt aiosqlite python-multipart apscheduler pydantic -q

echo "Starting KB Ingestor Admin Dashboard on http://localhost:8000"
echo "  API docs: http://localhost:8000/docs"
echo ""

cd "$SCRIPT_DIR/backend"
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
