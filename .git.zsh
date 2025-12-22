# export GIT_PAGER="delta --show-syntax-themes --dark"
if exists delta; then
  export GIT_PAGER='delta --side-by-side -w ${FZF_PREVIEW_COLUMNS:-$COLUMNS}'
fi

if exists gittool; then
  alias gst2="gittool verify_before_push ."
fi

if exists lazygit; then
  alias lg="lazygit"
fi

alias gdiffs="git diff --submodule=diff"

gfj() {
  git fetch --recurse-submodules=yes --jobs=16
}
