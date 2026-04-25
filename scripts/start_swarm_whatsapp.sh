#!/usr/bin/env bash
# start_swarm_whatsapp.sh - boot Alice's local WhatsApp bridge.
#
# Default safety posture:
#   - replies only after an explicit "Alice ..." trigger
#   - group chats muted
#   - no autonomous outbound injection

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BRIDGE_DIR="$REPO_ROOT/Network/whatsapp_bridge"
export PATH="/opt/homebrew/bin:$PATH"
PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3)"
fi
NODE_BIN="$(command -v node || true)"
if [ -z "$NODE_BIN" ] && [ -x "/opt/homebrew/bin/node" ]; then
  NODE_BIN="/opt/homebrew/bin/node"
fi
if [ -z "$NODE_BIN" ] && [ -x "/Applications/Codex.app/Contents/Resources/node" ]; then
  NODE_BIN="/Applications/Codex.app/Contents/Resources/node"
fi
if [ -z "$NODE_BIN" ]; then
  echo "[ERROR] Node.js was not found. Install it with: brew install node"
  exit 1
fi
export PYTHONPATH="$REPO_ROOT:${PYTHONPATH:-}"
export SIFTA_WHATSAPP_REQUIRE_TRIGGER="${SIFTA_WHATSAPP_REQUIRE_TRIGGER:-1}"
export SIFTA_WHATSAPP_TRIGGER="${SIFTA_WHATSAPP_TRIGGER:-alice}"
export SIFTA_WHATSAPP_ALLOW_GROUPS="${SIFTA_WHATSAPP_ALLOW_GROUPS:-0}"
export SIFTA_WHATSAPP_ENABLE_INJECT="${SIFTA_WHATSAPP_ENABLE_INJECT:-0}"

cd "$REPO_ROOT"

echo ""
echo "============================================================"
echo " Alice WhatsApp bridge"
echo " Trigger: ${SIFTA_WHATSAPP_TRIGGER}"
echo " Group chats: ${SIFTA_WHATSAPP_ALLOW_GROUPS}"
echo " Injection: ${SIFTA_WHATSAPP_ENABLE_INJECT}"
echo "============================================================"
echo ""

# 1. Install Baileys bridge deps if needed.
if [ ! -d "$BRIDGE_DIR/node_modules" ]; then
  echo "[SETUP] Installing Baileys bridge dependencies..."
  cd "$BRIDGE_DIR"
  npm install
  cd "$REPO_ROOT"
  echo "[SETUP] Done."
fi

# 2. Clear old local bridge listeners.
echo "[SETUP] Clearing port 7434..."
lsof -ti:7434 | xargs kill -9 2>/dev/null || true
echo "[SETUP] Clearing port 3001..."
lsof -ti:3001 | xargs kill -9 2>/dev/null || true
sleep 1

# 3. Start the Alice reply server in the background.
echo "[1/2] Starting Alice WhatsApp reply server (127.0.0.1:7434)..."
"$PYTHON_BIN" "$REPO_ROOT/Applications/alice_whatsapp_bridge.py" &
SIFTA_PID=$!
trap 'kill "$SIFTA_PID" 2>/dev/null || true' EXIT
sleep 1

# 4. Start Baileys QR bridge.
echo "[2/2] Starting WhatsApp Bridge (Baileys)..."
echo "      Open WhatsApp on your phone"
echo "      Tap Linked Devices -> Link a Device"
echo "      Scan the QR code below if one appears"
echo "      Then text: Alice hello"
echo ""
cd "$BRIDGE_DIR"
"$NODE_BIN" bridge.js

echo ""
echo "[SIFTA] WhatsApp bridge stopped."
