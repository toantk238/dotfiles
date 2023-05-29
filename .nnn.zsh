if [ -f /usr/share/nnn/quitcd/quitcd.bash_sh_zsh ]; then
    source /usr/share/nnn/quitcd/quitcd.bash_sh_zsh
fi

[ -n "$NNNLVL" ] && PS1="N$NNNLVL $PS1"
[ -f /etc/profile.d/autojump.zsh ] && source /etc/profile.d/autojump.zsh
export NNN_FIFO=/tmp/nnn.fifo
NNN_FCOLORS='c1e2272e006033f7c6d6abc4'
nnn_cd()                                                                                                   
{
    if ! [ -z "$NNN_PIPE" ]; then
        printf "%s\0" "0c${PWD}" > "${NNN_PIPE}" !&
    fi  
}

trap nnn_cd EXIT


NNN_PLUG_INLINE='e:!go run "$nnn"*'
NNN_PLUG_DEFAULT='1:ipinfo;p:preview-tui;o:fzz;b:nbak;f:fzcd'
NNN_PLUG="$NNN_PLUG_DEFAULT;$NNN_PLUG_INLINE"
export NNN_ICONLOOKUP=1
export NNN_PLUG
export PAGER='less -R'
export EDITOR=nvim
