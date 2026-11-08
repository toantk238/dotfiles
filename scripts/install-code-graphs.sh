#!/usr/bin/env bash
# Install the code-graph tools Claude Code uses (macOS + Linux, idempotent).
#   code-review-graph  -> uv tool (one copy in ~/.local/bin, shared by hooks + MCP)
#   codegraph          -> npm global (@colbymchenry/codegraph)
# MCP servers and hooks are configured elsewhere (.claude_custom/); per-project
# graphs are built once with `codegraph init -i` and `code-review-graph build`.
# Re-run with UPGRADE=1 to upgrade instead of skipping installed tools.
set -euo pipefail

have() { command -v "$1" >/dev/null 2>&1; }
UPGRADE="${UPGRADE:-0}"

if have uv; then
  if have code-review-graph && [ "$UPGRADE" != 1 ]; then
    echo "code-review-graph: already installed ($(code-review-graph --version))"
  else
    uv tool install --upgrade code-review-graph
  fi
else
  echo "uv not found; install it first (brew install uv)" >&2
  exit 1
fi

if have codegraph && [ "$UPGRADE" != 1 ]; then
  echo "codegraph: already installed ($(codegraph --version))"
elif have npm; then
  npm install -g @colbymchenry/codegraph
else
  echo "npm not found; run 'mise install node' first" >&2
  exit 1
fi
