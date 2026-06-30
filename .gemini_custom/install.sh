#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGY_CLI_DIR="$HOME/.gemini/antigravity-cli"
AGY_HOOKS_DIR="$HOME/.gemini/hooks"

echo "Installing .gemini_custom..."

# Symlink settings.json
if [ -f "$AGY_CLI_DIR/settings.json" ] && [ ! -L "$AGY_CLI_DIR/settings.json" ]; then
  cp "$AGY_CLI_DIR/settings.json" "$AGY_CLI_DIR/settings.json.backup.$(date +%Y%m%d_%H%M%S)"
  echo "Backed up existing settings.json"
fi
ln -sf "$SCRIPT_DIR/settings.json" "$AGY_CLI_DIR/settings.json"
echo "  ✓ settings.json → $AGY_CLI_DIR/settings.json"

# Symlink hooks directory
if [ -e "$AGY_HOOKS_DIR" ] && [ ! -L "$AGY_HOOKS_DIR" ]; then
  echo "  WARNING: $AGY_HOOKS_DIR exists and is not a symlink — rename it first"
  exit 1
fi
ln -sf "$SCRIPT_DIR/hooks" "$AGY_HOOKS_DIR"
echo "  ✓ hooks/ → $AGY_HOOKS_DIR"

# Bootstrap Python venv
cd "$SCRIPT_DIR/hooks"
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q pytest
  echo "  ✓ .venv created"
fi

echo ""
echo "Done. Verify hooks with: agy /hooks"
echo "If hooks are not listed, AGY may not load hooks from settings.json."
echo "Fallback: create ~/.gemini/antigravity-cli/hooks.json with the 'hooks' key from settings.json."
