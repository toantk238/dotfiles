# export GIT_PAGER="delta --show-syntax-themes --dark"
export GIT_PAGER="delta"

if exists gittool; then
  alias gst2="gittool verify_before_push ."
fi
