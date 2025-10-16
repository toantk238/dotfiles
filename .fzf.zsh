#!/bin/zsh
#
#export FZF_DEFAULT_COMMAND="rg --no-ignore --hidden --files -g '!.git/' "
export FZF_DEFAULT_COMMAND="fd --type f -HI --exclude .git --exclude .gradle --exclude .transforms --exclude .idea --exclude node_modules --exclude __pycache__ --exclude .mypy_cache --exclude Localizable.strings --exclude Generated"

export FZF_DEFAULT_OPTS='--height 70% --layout=reverse --border'

export FZF_ALT_C_COMMAND='fd --type directory'

export RG_FZF_OPTS=$(cat <<END
-i \\
--no-ignore --hidden \\
-g '!Pods/' \\
-g '!Text.swift' \\
-g '!*.pbxproj' \\
-g '!DerivedData/'
-g '!Localizable.strings'
-g '!Generated/'
END
)

function rg_fzf() {
  rg_cmd=$(cat <<END
rg --color=always --line-number \\
--no-heading "${*:-}" $RG_FZF_OPTS
END
  )
  fzf_cmd=$(cat <<END
fzf --ansi \\
			--color "hl:-1:underline,hl+:-1:underline:reverse" \\
			--delimiter : \
			--preview 'bat --color=always {1} --highlight-line {2}' \\
			--preview-window 'up,60%,border-bottom,+{2}+3/3,~3' \\
			--bind 'ctrl-w:unix-word-rubout+top,ctrl-u:unix-line-discard+top' \\
			--bind 'change:top' \\
      --bind 'enter:become(nvim {1} +{2})'
END
)

  full_cmd=$(cat <<END
$rg_cmd |
$fzf_cmd
END
 )
  eval "$full_cmd"
}

