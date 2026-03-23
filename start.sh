#!/bin/bash
# ─────────────────────────────────────────────
#   AI Arena — One-Command Launcher
# ─────────────────────────────────────────────
set -e
cd "$(dirname "$0")/backend"

if [ ! -f .env ]; then
  cp .env.example .env
  echo ""
  echo "  ✅  Created backend/.env from .env.example"
  echo "  📝  Add your OpenRouter key to backend/.env"
  echo "      or use the in-app Settings panel after launch."
  echo ""
fi

echo "📦 Installing dependencies..."
pip install -r requirements.txt --break-system-packages -q

echo ""
echo "  ⚔  AI Arena — OpenRouter Edition"
echo "  ─────────────────────────────────"
echo "  App:      http://localhost:3001"
echo "  API docs: http://localhost:3001/docs"
echo "  Ctrl+C to stop"
echo ""

python main.py
