#!/usr/bin/env zsh

# Install required apps
# set -x

# clean Yay cache
rm -rf  ~/.cache/yay/completion.cache

apps=(
 ibus-bamboo
  # Browsers
 google-chrome
  # Chat apps
 slack-desktop telegram-desktop
  # Android
 scrcpy  
 # Docker
 docker docker-compose 

 # Terminal
 zsh fd ripgrep fzf uctags-git tmux 

 # Development
 neovim 
 pyenv pyenv-virtualenv python-pip 
 npm yarn nodejs 

 # Git
 git-delta lazygit forgit 

 # Fonts
 ttf-clear-sans nerd-fonts-meslo ttf-meslo-nerd-font-powerlevel10k ttf-jetbrains-mono-nerd 

 # Gnome Stuff
 gconf filemanager-actions gnome-browser-connector gnome-system-monitor dconf-editor nautilus-open-any-terminal 

 # Multimedia
 vlc 

 # Others
 neofetch syncthing 
 pet-bin 
 direnv xclip prettier gtk2 wl-clipboard rclone crow-translate fluent-reader-bin libvncserver lemonade-git net-tools watchman-bin bat tmuxp tldr nnn-nerd autojump lazydocker-bin nordvpn-bin
)

yay -S --needed ${apps[@]}


# Setup zsh + Oh-my-zsh

sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"
git clone https://github.com/zsh-users/zsh-autosuggestions ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/plugins/zsh-autosuggestions
git clone https://github.com/zsh-users/zsh-syntax-highlighting.git ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/plugins/zsh-syntax-highlighting
git clone https://github.com/wfxr/forgit.git ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/plugins/forgit
git clone https://github.com/Aloxaf/fzf-tab ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/plugins/fzf-tab
