# carapace: completions for 1000+ CLIs, bridging to zsh/fish/bash completers
if exists carapace; then
  export CARAPACE_BRIDGES='zsh,fish,bash,inshellisense'
  zstyle ':completion:*' format $'\e[2;37mCompleting %d\e[m'
  source <(carapace _carapace)
  # fzf-tab's default query-string (prefix input first) seeds fzf with the typed word when the
  # candidates share no display prefix. carapace adds whole words (~/Downloads/x) without
  # `compadd -p`, so `mv ~/Downloads/<Tab>` queried "~/Downloads/" against bare names -> 0 items.
  # Seed the query from the displayed candidates only. Drop once fixed upstream:
  # https://github.com/Aloxaf/fzf-tab/issues/601
  zstyle ':fzf-tab:*' query-string prefix first
fi
