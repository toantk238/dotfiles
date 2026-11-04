function sesh-sessions() {
  {
    exec </dev/tty
    exec <&1
    local session
    session=$(sesh list -t -c | fzf --height 40% --reverse --border-label ' sesh ' --border --prompt '⚡  ')
    zle reset-prompt >/dev/null 2>&1 || true
    [[ -z "$session" ]] && return
    sesh connect $session
  }
}

zle -N sesh-sessions
bindkey -M emacs '\es' sesh-sessions
bindkey -M vicmd '\es' sesh-sessions
bindkey -M viins '\es' sesh-sessions

# The session name sesh derives for <dir>: git root basename + subpath, else the
# dir basename; tmux can't have . or : in a name, so they become _.
_sesh_dir_name() {
  local dir=$1 root name
  root=$(git -C "$dir" rev-parse --show-toplevel 2>/dev/null)
  if [[ -n "$root" ]]; then
    name="${root:t}${dir#$root}"
  else
    name="${dir:t}"
  fi
  print -r -- "${${name//./_}//:/_}"
}

# Open a session for <target> even if one already exists, as name-2, name-3, ...
# <target>: tmux session name, configured sesh session name or dir (default: cwd).
# Only a first session goes through sesh, so suffixed ones skip startup_command.
_sesh_new() {
  local target="${1:-.}" tab=$'\t' row base dir name n=2
  row=$({
    tmux list-sessions -F "#S${tab}#{session_path}" 2>/dev/null
    sesh list -c --format "{name}${tab}{path}"
  } | awk -F'\t' -v t="$target" '$1 == t { print; exit }')

  if [[ -n "$row" ]]; then
    base="${row%%$tab*}"
    dir="${row#*$tab}"
  elif [[ -d "$target" ]]; then
    dir="${target:A}"
    base=$(_sesh_dir_name "$dir")
  else
    echo "s: no session or directory named '$target'" >&2
    return 1
  fi

  if ! tmux has-session -t "=$base" 2>/dev/null; then
    sesh connect "$target"
    return
  fi

  name="$base-$n"
  while tmux has-session -t "=$name" 2>/dev/null; do
    name="$base-$((++n))"
  done
  tmux new-session -d -s "$name" -c "$dir" || return
  if [[ -n "$TMUX" ]]; then
    tmux switch-client -t "=$name"
  else
    tmux attach-session -t "=$name"
  fi
}

# Sesh smart session manager function
#   s                  pick a session
#   s <target>         connect (reuses an existing session)
#   s -n [target]      always a new session, suffixed if the name is taken
s() {
  if [[ "$1" == "-n" || "$1" == "--new" ]]; then
    shift
    _sesh_new "$@"
  elif [ $# -eq 0 ]; then
    # No arguments: show interactive picker (without icons to avoid parsing issues)
    local selected=$(sesh list | fzf \
      --height 50% \
      --border rounded \
      --border-label ' sesh sessions ' \
      --prompt '⚡ ' \
      --header 'Tips: Start typing to filter | Enter to connect | Esc to cancel' \
      --preview 'sesh preview {}' \
      --preview-window right:55%)

    [[ -z "$selected" ]] && return 0
    sesh connect "$selected"
  else
    # Arguments provided: pass directly to sesh
    sesh connect "$@"
  fi
}

# Sesh aliases for quick access
alias sl='sesh list --icons'             # List all sessions with icons
alias sn='sesh connect $(basename $PWD)' # New session named after current dir
alias sls='sesh list -t --icons'         # List only tmux sessions
