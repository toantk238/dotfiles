#!/usr/bin/env bash
# One-off: copy existing nvm/luaenv installs into mise (no re-download).
# Copies (not `mise link`), so the old managers' dirs can be deleted afterwards.
# Run after installing mise. Safe to re-run.
set -euo pipefail
command -v mise >/dev/null || { echo "install mise first: sudo pacman -S mise"; exit 1; }

installs="${MISE_DATA_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/mise}/installs"
copy_into_mise() { # <tool> <version> <src dir>
  local dst="$installs/$1/$2"
  [ -e "$dst" ] && return
  mkdir -p "$installs/$1" && cp -a "$3" "$dst" && echo "copied $1@$2"
}
for d in "$HOME"/.nvm/versions/node/v*; do
  [ -d "$d" ] && copy_into_mise node "${d##*/v}" "$d"
done
for d in "$HOME"/.luaenv/versions/*; do
  [ -d "$d" ] && copy_into_mise lua "${d##*/}" "$d"
done
mise reshim

mise install   # anything in ~/.config/mise/config.toml still missing
mise ls
echo "Once happy, the old ~/.nvm ~/.goenv ~/.luaenv ~/.rvm dirs can be removed,"
echo "and NVM_LAZY_LOAD dropped from ~/.env.zsh."
