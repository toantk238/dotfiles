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

# Sesh smart session manager function
s() {
  if [ $# -eq 0 ]; then
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
