export FORGIT_FZF_DEFAULT_OPTS="
--exact
--border
--cycle
--reverse
--height '80%'
"
if exists pbcopy; then
	export FORGIT_COPY_CMD="pbcopy"
elif exists wl-copy; then
	export FORGIT_COPY_CMD='wl-copy'
elif exists lemonade; then
	export FORGIT_COPY_CMD='lemonade copy'
fi
export FORGIT_LOG_FZF_OPTS='
--bind="ctrl-e:execute(echo {} |grep -Eo [a-f0-9]+ |head -1 |xargs git show |nvim -)"
'
export FORGIT_CHECKOUT_BRANCH_BRANCH_GIT_OPTS='--sort=-committerdate'
