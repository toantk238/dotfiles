if [ -f /usr/share/nnn/quitcd/quitcd.bash_sh_zsh ]; then
	source /usr/share/nnn/quitcd/quitcd.bash_sh_zsh
fi

if [ -f ~/.config/nnn/quitcd/quitcd.bash_sh_zsh ]; then
	source ~/.config/nnn/quitcd/quitcd.bash_sh_zsh
fi

[ -n "$NNNLVL" ] && PS1="N$NNNLVL $PS1"
export NNN_FIFO=/tmp/nnn.fifo
NNN_FCOLORS='c1e2272e006033f7c6d6abc4'
nnn_cd() {
	if ! [ -z "$NNN_PIPE" ]; then
		printf "%s\0" "0c${PWD}" ! >"${NNN_PIPE}" &
	fi
}

trap nnn_cd EXIT

NNN_PLUG_INLINE='e:!go run "$nnn"*'
NNN_PLUG_DEFAULT='1:gitroot;p:preview-tui;o:fzz;b:nbak;f:fzcd;2:xdgdefault'
NNN_PLUG="$NNN_PLUG_DEFAULT;$NNN_PLUG_INLINE"
export NNN_ICONLOOKUP=0
export NNN_PLUG
export PAGER='less -R'
export EDITOR=nvim
alias n="n -deH"
