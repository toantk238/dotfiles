claude_hooks_log() {
  if exists tspin; then
    tspin -f ~/.claude/hooks/stop_router.log
  else
    tail -f ~/.claude/hooks/stop_router.log
  fi
}

claude() {
    local arg sub=0 pdir
    local -a penv
    # Profile (.claude-profile.sh): $CLAUDE_PROFILE, usually set by direnv,
    # picks the config dir for this run; local -x scopes it to this call.
    if [[ -n "$CLAUDE_PROFILE" ]] && (( $+functions[_claude_profile_dir] )); then
        pdir="$(_claude_profile_dir)" || return
        local -x CLAUDE_CONFIG_DIR
        if [[ -n "$pdir" ]]; then
            CLAUDE_CONFIG_DIR="$pdir"
            # Per-profile env (KEY=VALUE lines), e.g.
            # ENABLE_CLAUDEAI_MCP_SERVERS=false to drop claude.ai connectors.
            [[ -f "$pdir/profile.env" ]] &&
                penv=(${(f)"$(grep -Ev '^[[:space:]]*(#|$)' "$pdir/profile.env")"})
        else
            unset CLAUDE_CONFIG_DIR
        fi
    fi
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
        command env "${penv[@]}" claude "$@"
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
    [[ -n "$CLAUDE_PROFILE" ]] && label="[$CLAUDE_PROFILE] $label"
    [[ -n "$SSH_CONNECTION" ]] && label="${HOST%%.*}:$label"

    prev="$(tmux display-message -p '#{automatic-rename}' 2>/dev/null)"
    prev_name="$(tmux display-message -p '#{window_name}' 2>/dev/null)"
    tmux set-window-option automatic-rename off >/dev/null 2>&1
    tmux rename-window "🤖 $label" >/dev/null 2>&1
    command env "${penv[@]}" claude "$@"
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

alias c="claude"
