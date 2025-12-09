#!/usr/bin/env zsh

# Setup
ya pkg add yazi-rs/plugins:git
ya pkg add yazi-rs/plugins:piper
ya pkg add yazi-rs/flavors:dracula
ya pkg add yazi-rs/plugins:types

git clone https://github.com/DreamMaoMao/fg.yazi.git ~/.config/yazi/plugins/fg.yazi


git clone https://github.com/Sonico98/yazi-prompt.sh ./yazi-prompt && \
chmod +x ./yazi-prompt/zsh/p10k/yazi_p10k.zsh && \
cp ./yazi-prompt/zsh/p10k/yazi_p10k.zsh "$ZDOTDIR"/.yazi_p10k.zsh && \
sed 's/  # If p10k is already loaded, reload configuration./  source "$ZDOTDIR"\/.yazi_p10k.zsh×  # If p10k is already loaded, reload configuration./' ~/.p10k.zsh | tr '×' '\n' >| ~/.p10k.zsh.tmp && yes | mv ~/.p10k.zsh{.tmp,} && \
rm -rf ./yazi-prompt
