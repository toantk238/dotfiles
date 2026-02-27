# SSH agent - reuse existing agent or start a new one
if [ -z "$SSH_TTY" ]; then  # not in an SSH session
  SSH_ENV="$HOME/.ssh/agent-env"
  if [ -f "$SSH_ENV" ]; then
    source "$SSH_ENV" > /dev/null
    # Check if the agent is still running
    kill -0 "$SSH_AGENT_PID" 2>/dev/null || {
      eval "$(ssh-agent -s)" > /dev/null
      echo "SSH_AUTH_SOCK=$SSH_AUTH_SOCK; export SSH_AUTH_SOCK;" > "$SSH_ENV"
      echo "SSH_AGENT_PID=$SSH_AGENT_PID; export SSH_AGENT_PID;" >> "$SSH_ENV"
    }
  else
    eval "$(ssh-agent -s)" > /dev/null
    mkdir -p "$HOME/.ssh"
    echo "SSH_AUTH_SOCK=$SSH_AUTH_SOCK; export SSH_AUTH_SOCK;" > "$SSH_ENV"
    echo "SSH_AGENT_PID=$SSH_AGENT_PID; export SSH_AGENT_PID;" >> "$SSH_ENV"
    chmod 600 "$SSH_ENV"
  fi
fi
