# export GIT_PAGER="delta --show-syntax-themes --dark"
if exists delta; then
  export GIT_PAGER='delta --side-by-side -w ${FZF_PREVIEW_COLUMNS:-$COLUMNS}'
fi

if exists gittool; then
  alias gst2="gittool verify_before_push ."

  # zsh completion = `eval "$(gittool completion zsh)"`, cached so new shells skip
  # `uv run`; regenerated whenever gittool's sources are newer than the cache.
  if [ -n "$ZSH_VERSION" ]; then
    () {
      local src=${${commands[gittool]}:A:h}
      local cache=${XDG_CACHE_HOME:-$HOME/.cache}/gittool/completion.zsh
      local f stale=0
      [[ -s $cache ]] || stale=1
      for f in $src/gittool $src/helper/*.py(N); do
        [[ $f -nt $cache ]] && stale=1
      done
      if (( stale )); then
        mkdir -p ${cache:h}
        gittool completion zsh >| $cache.tmp && command mv -f $cache.tmp $cache
      fi
      [[ -s $cache ]] && source $cache
    }
  fi
fi

if exists lazygit; then
  alias lg="lazygit"
fi

alias gdiffs="git diff --submodule=diff"
alias gclean="git clean -dff && git submodule foreach git clean -dff"

gfj() {
  git fetch --recurse-submodules=yes --jobs=16
}
