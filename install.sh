#!/usr/bin/env bash
# Symlink dotfiles into $HOME (see install.conf.yaml). Packages: scripts/linux.sh
set -euo pipefail
cd "$(dirname "$(realpath "$0")")"
exec uvx dotbot -d . -c install.conf.yaml "$@"
