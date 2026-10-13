# mise: polyglot version manager (replaces nvm/goenv/luaenv/rvm)
# Global tools: ~/.config/mise/config.toml   Per project: mise.toml / .tool-versions / .nvmrc
eval "$(mise activate zsh)"

# bun
[ -s "$HOME/.bun/_bun" ] && source "$HOME/.bun/_bun"
export BUN_INSTALL="$HOME/.bun"
