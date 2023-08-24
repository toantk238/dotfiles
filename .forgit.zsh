export FORGIT_FZF_DEFAULT_OPTS="
--exact
--border
--cycle
--reverse
--height '80%'
"
if exists wl-copy; then
  export FORGIT_COPY_CMD='wl-copy'
elif exists lemonade; then
  export FORGIT_COPY_CMD='lemonade copy'
fi

