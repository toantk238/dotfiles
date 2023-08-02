#!/bin/zsh
#
function search_fzf(){
  rg --color=always --line-number -i --no-heading "${*:-}" |
  fzf --ansi \
      --color "hl:-1:underline,hl+:-1:underline:reverse" \
      --delimiter : \
      --preview 'bat --color=always {1} --highlight-line {2}' \
      --preview-window 'up,60%,border-bottom,+{2}+3/3,~3' \
      --bind 'ctrl-w:unix-word-rubout+top,ctrl-u:unix-line-discard+top' \
      --bind 'change:top' \
      --bind 'enter:become(nvim {1} +{2})'
}
