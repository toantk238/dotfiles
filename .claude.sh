claude_hooks_log() {
  if exists tspin; then
    tspin -f ~/.claude/hooks/stop_router.log
  elif 
    tail -f ~/.claude/hooks/stop_router.log
}

claude() {
    local arg sub=0
    case "$1" in
        agents|mcp|config|setup-token|update|doctor|install|migrate-installer)
            sub=1 ;;
    esac
    for arg in "$@"; do
        case "$arg" in
            -p|--print) sub=1 ;;
        esac
    done

    if (( sub )) || [[ -z "$TMUX" ]]; then
        command claude "$@"
        return
    fi

    # Window label = <project>[/<branch>] from the git repo root. The yadm-
    # managed $HOME is not a plain git repo, so fall back to yadm's branch
    # there; short hostname prefix over SSH.
    local root label branch prev prev_name ret
    root="$(git rev-parse --show-toplevel 2>/dev/null)"
    if [[ -n "$root" ]]; then
        label="${root:t}"
        branch="$(git symbolic-ref --quiet --short HEAD 2>/dev/null)"
    elif [[ "$PWD" == "$HOME" ]]; then
        label="home"
        branch="$(yadm rev-parse --abbrev-ref HEAD 2>/dev/null)"
    else
        label="${PWD:t}"
        branch=""
    fi
    case "$branch" in
        "" | main | master | trunk) ;;
        *) label="$label/$branch" ;;
    esac
    [[ -n "$SSH_CONNECTION" ]] && label="${HOST%%.*}:$label"

    prev="$(tmux display-message -p '#{automatic-rename}' 2>/dev/null)"
    prev_name="$(tmux display-message -p '#{window_name}' 2>/dev/null)"
    tmux set-window-option automatic-rename off >/dev/null 2>&1
    tmux rename-window "🤖 $label" >/dev/null 2>&1
    command claude "$@"
    ret=$?
    # Restore on exit: if the window had a manual name (automatic-rename was
    # off), put that name back; otherwise re-enable tmux's auto-renaming.
    if [[ "$prev" == "0" ]]; then
        tmux rename-window "$prev_name" >/dev/null 2>&1
    else
        tmux set-window-option automatic-rename on >/dev/null 2>&1
    fi
    return $ret
}
