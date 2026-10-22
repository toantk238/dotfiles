#!/usr/bin/env bash
# Register the dotfiles' GNOME custom keybindings. Paths resolve from this checkout, so the
# repo can live anywhere. Entries live under .../custom-keybindings/dotfiles-<id>/; custom
# shortcuts made in GNOME Settings (customN) are left alone. Idempotent.
set -euo pipefail
DOTFILES=$(cd "$(dirname "$0")/.." && pwd)
command -v gsettings >/dev/null || { echo 'gsettings not found, skipping GNOME keybindings'; exit 0; }

# id | binding | command | name
KEYBINDINGS=(
  "curl-hurl|<Super>i|$DOTFILES/scripts/convert_curl_hurl.sh|Convert curl to hurl and vice versa"
  "scrcpy-all|<Super><Shift>l|$DOTFILES/scripts/scrcpy_all.sh|Mirror all android devices"
  "restart-ibus|<Control><Shift>i|$DOTFILES/scripts/restart_ibus.sh|Restart ibus"
  "kitty-session-dump|<Super><Shift>s|$HOME/.local/bin/kitty-session dump --all|Dump kitty sessions"
  "kitty-session-restore|<Super><Shift>r|$HOME/.local/bin/kitty-session restore|Restore kitty sessions"
)

SCHEMA=org.gnome.settings-daemon.plugins.media-keys
BASE=/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings

# Keep entries not owned by this script, but drop any that grab a key we bind (e.g. an
# older hand-made customN for the same shortcut).
ours=$(printf '%s\n' "${KEYBINDINGS[@]}" | cut -d'|' -f2)
paths=()
for p in $(gsettings get $SCHEMA custom-keybindings | grep -o "'[^']*'" | tr -d "'"); do
  [[ $p == "$BASE/dotfiles-"* ]] && continue
  binding=$(gsettings get $SCHEMA.custom-keybinding:"$p" binding | tr -d "'")
  if grep -qxF -- "$binding" <<<"$ours"; then
    echo "replacing $p ($binding)"
    dconf reset -f "$p"
    continue
  fi
  paths+=("$p")
done

for entry in "${KEYBINDINGS[@]}"; do
  IFS='|' read -r id binding command name <<<"$entry"
  p="$BASE/dotfiles-$id/"
  gsettings set $SCHEMA.custom-keybinding:"$p" name "$name"
  gsettings set $SCHEMA.custom-keybinding:"$p" command "$command"
  gsettings set $SCHEMA.custom-keybinding:"$p" binding "$binding"
  paths+=("$p")
done

list=$(printf "'%s', " "${paths[@]}")
gsettings set $SCHEMA custom-keybindings "[${list%, }]"
echo "GNOME keybindings applied (${#KEYBINDINGS[@]} from dotfiles)"
