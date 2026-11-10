# mise: polyglot version manager (replaces nvm/goenv/luaenv/rvm)
# Global tools: ~/.config/mise/config.toml   Per project: mise.toml / .tool-versions / .nvmrc

# A system-wide rvm (/etc/profile.d/rvm.sh, sourced by login shells) exports
# GEM_HOME/GEM_PATH and puts its rubies first in PATH. Once mise has a ruby,
# drop all of that so gems go into mise's ruby, not rvm's.
if [[ -n $rvm_path ]] && mise which ruby &>/dev/null; then
  () {
    zmodload -F zsh/parameter p:functions_source
    # every function rvm defined (rvm, __rvm_*, gemset_*, its `gem` wrapper, ...)
    local -a rvm_fns=(${(k)functions_source[(R)$rvm_path/*]})
    (( $#rvm_fns )) && unfunction $rvm_fns
    path=(${path:#$rvm_path/*})
    # mise rebuilds PATH from this one, inherited from the parent shell
    if [[ -n $__MISE_ORIG_PATH ]]; then
      local -a orig=(${(s.:.)__MISE_ORIG_PATH})
      export __MISE_ORIG_PATH=${(j.:.)${orig:#$rvm_path/*}}
    fi
  }
  unset GEM_HOME GEM_PATH MY_RUBY_HOME RUBY_VERSION IRBRC
  unset -m 'rvm_*'
fi

eval "$(mise activate zsh)"

# bun
[ -s "$HOME/.bun/_bun" ] && source "$HOME/.bun/_bun"
export BUN_INSTALL="$HOME/.bun"
