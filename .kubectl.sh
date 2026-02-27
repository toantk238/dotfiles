if exists kubectl; then
  alias k="kubectl"
  kubectl completion zsh > "${fpath[1]}/_kubectl"
fi
