# pnpm global bin dir: pnpm refuses `add -g` / `update -g` unless it is on PATH.
# Defaults match what `pnpm setup` would write for each OS.
if exists pnpm; then
  if osis Darwin; then
    export PNPM_HOME="${PNPM_HOME:-$HOME/Library/pnpm}"
  else
    export PNPM_HOME="${PNPM_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/pnpm}"
  fi
  case ":$PATH:" in
    *":$PNPM_HOME/bin:"*) ;;
    *) export PATH="$PNPM_HOME/bin:$PATH" ;;
  esac
fi
