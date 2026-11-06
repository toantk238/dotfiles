#!/usr/bin/env bash
# Symlink dotfiles into $HOME (see install.conf.yaml). Packages: scripts/linux.sh
set -euo pipefail
cd "$(dirname "$(realpath "$0")")"
# `uv tool run` == `uvx`, but avoids a stray ~/.local/bin/uvx whose sibling uv is missing.
exec uv tool run dotbot -d . -c install.conf.yaml "$@"
