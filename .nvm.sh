[ -z "$NVM_DIR" ] && export NVM_DIR="$HOME/.nvm"

_nvm_setup_nvmrc_hook() {
  autoload -U add-zsh-hook

  load-nvmrc() {
    local nvmrc_path
    nvmrc_path="$(nvm_find_nvmrc)"

    if [ -n "$nvmrc_path" ]; then
      local nvmrc_node_version
      nvmrc_node_version=$(nvm version "$(cat "${nvmrc_path}")")

      if [ "$nvmrc_node_version" = "N/A" ]; then
        nvm install
      elif [ "$nvmrc_node_version" != "$(nvm version)" ]; then
        nvm use
      fi
    elif [ -n "$(PWD=$OLDPWD nvm_find_nvmrc)" ] && [ "$(nvm version)" != "$(nvm version default)" ]; then
      echo "Reverting to nvm default version"
      nvm use default
    fi
  }

  add-zsh-hook chpwd load-nvmrc
  load-nvmrc
}

# NVM_LAZY_LOAD=false (or 0) to eagerly load nvm at shell startup.
# Defaults to lazy loading to avoid the ~300ms startup penalty.
if [[ "${NVM_LAZY_LOAD:-true}" == "false" || "${NVM_LAZY_LOAD}" == "0" ]]; then
  # Eager load
  [ -f "$NVM_DIR/nvm.sh" ] && source "$NVM_DIR/nvm.sh"
  _nvm_setup_nvmrc_hook
else
  # Lazy-load: defer sourcing until nvm/node/npm/npx is first invoked
  _nvm_lazy_load() {
    unfunction nvm node npm npx 2>/dev/null
    [ -f "$NVM_DIR/nvm.sh" ] && source "$NVM_DIR/nvm.sh"
    _nvm_setup_nvmrc_hook
  }

  nvm() { _nvm_lazy_load; nvm "$@"; }
  node() { _nvm_lazy_load; node "$@"; }
  npm() { _nvm_lazy_load; npm "$@"; }
  npx() { _nvm_lazy_load; npx "$@"; }
fi

[ -s "$HOME/.bun/_bun" ] && source "$HOME/.bun/_bun"

# bun
export BUN_INSTALL="$HOME/.bun"
