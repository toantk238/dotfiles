#!/bin/zsh
#
#export FZF_DEFAULT_COMMAND="rg --no-ignore --hidden --files -g '!.git/' "
export FZF_DEFAULT_COMMAND="fd --type f -HI --exclude .git --exclude .gradle --exclude .transforms --exclude .idea"

export FZF_DEFAULT_OPTS='--height 70% --layout=reverse --border'

export FZF_ALT_C_COMMAND='fd --type directory'

function rg_fzf() {
	rg --hidden --color=always --line-number -i --no-heading "${*:-}" |
		fzf --ansi \
			--color "hl:-1:underline,hl+:-1:underline:reverse" \
			--delimiter : \
			--preview 'bat --color=always {1} --highlight-line {2}' \
			--preview-window 'up,60%,border-bottom,+{2}+3/3,~3' \
			--bind 'ctrl-w:unix-word-rubout+top,ctrl-u:unix-line-discard+top' \
			--bind 'change:top' \
			--bind 'enter:become(nvim {1} +{2})'
}
