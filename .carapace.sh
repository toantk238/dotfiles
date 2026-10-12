# carapace: completions for 1000+ CLIs, bridging to zsh/fish/bash completers
if exists carapace; then
  export CARAPACE_BRIDGES='zsh,fish,bash,inshellisense'
  zstyle ':completion:*' format $'\e[2;37mCompleting %d\e[m'
  source <(carapace _carapace)
fi
