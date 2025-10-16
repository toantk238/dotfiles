if exists ranger; then
  function y() {
    local tmp="$(mktemp -t "yazi-cwd.XXXXXX")" cwd
    yazi "$@" --cwd-file="$tmp"
    IFS= read -r -d '' cwd <"$tmp"
    [ -n "$cwd" ] && [ "$cwd" != "$PWD" ] && builtin cd -- "$cwd"
    rm -f -- "$tmp"
  }
  alias n=y
fi

# Setup
# ya pkg add yazi-rs/plugins:piper
# ya pack -a sanjinso/monokai-vibrant
# git clone https://github.com/DreamMaoMao/fg.yazi.git ~/.config/yazi/plugins/fg.yazi
