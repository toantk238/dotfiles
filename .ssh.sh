# SSH agent - reuse existing agent or start a new one
if [ -z "$SSH_TTY" ]; then # not in an SSH session
  SSH_ENV="$HOME/.ssh/agent-env"
  if [ -f "$SSH_ENV" ]; then
    source "$SSH_ENV" >/dev/null
    # Check if the agent is still running
    kill -0 "$SSH_AGENT_PID" 2>/dev/null || {
      eval "$(ssh-agent -s)" >/dev/null
      echo "SSH_AUTH_SOCK=$SSH_AUTH_SOCK; export SSH_AUTH_SOCK;" >"$SSH_ENV"
      echo "SSH_AGENT_PID=$SSH_AGENT_PID; export SSH_AGENT_PID;" >>"$SSH_ENV"
    }
  else
    eval "$(ssh-agent -s)" >/dev/null
    mkdir -p "$HOME/.ssh"
    echo "SSH_AUTH_SOCK=$SSH_AUTH_SOCK; export SSH_AUTH_SOCK;" >"$SSH_ENV"
    echo "SSH_AGENT_PID=$SSH_AGENT_PID; export SSH_AGENT_PID;" >>"$SSH_ENV"
    chmod 600 "$SSH_ENV"
  fi
fi

ssh-reload() {
  eval "$(ssh-agent)" && ssh-add -D
}

# Close cached SSH multiplex masters (ControlMaster/ControlPersist in .ssh/config).
# A master keeps the identity it first logged in with, so if one was opened with
# the wrong key every later git push reuses it ("Write access to repository not
# granted"). No args: close every master in ~/.ssh/cm-*; else only the given hosts.
# Then prints which GitHub account a fresh connection authenticates as.
# `command ssh` skips the kitty kitten alias, which refuses non-interactive use.
ssh-mux-reset() {
  local sock host
  if (( $# )); then
    for host in "$@"; do command ssh -O exit "$host"; done
  else
    for sock in ~/.ssh/cm-*(N=); do
      echo "closing ${sock:t}"
      command ssh -o ControlPath="$sock" -O exit _ 2>&1
    done
  fi
  command ssh -T git@github.com 2>&1 | grep -o 'Hi [^!]*!'
}
