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
	export FORGIT_COPY_CMD='lemonade copy --host=127.0.0.1'
fi

if exists delta; then
  export FORGIT_PAGER="delta"
fi

export FORGIT_LOG_FZF_OPTS='
--bind="ctrl-e:execute(echo {} |grep -Eo [a-f0-9]+ |head -1 |xargs git show |nvim -)"
'
export FORGIT_CHECKOUT_BRANCH_BRANCH_GIT_OPTS='--sort=-committerdate'

alias gloa="glo --all"
