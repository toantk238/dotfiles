[ -d $HOME/.luaenv/bin ] && export PATH=$HOME/.luaenv/bin:$PATH

if exists luaenv; then
  eval "$(luaenv init -)"
fi
