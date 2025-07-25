# Enable Powerlevel10k instant prompt. Should stay close to the top of ~/.zshrc.
# Initialization code that may require console input (password prompts, [y/n]
# confirmations, etc.) must go above this block; everything else may go below.

# (( ${+commands[direnv]} )) && emulate zsh -c "$(direnv export zsh)"

# if [[ -r "${XDG_CACHE_HOME:-$HOME/.cache}/p10k-instant-prompt-${(%):-%n}.zsh" ]]; then
#   source "${XDG_CACHE_HOME:-$HOME/.cache}/p10k-instant-prompt-${(%):-%n}.zsh"
# fi

(( ${+commands[direnv]} )) && emulate zsh -c "$(direnv hook zsh)"

THIS_USER=$(whoami)

# If you come from bash you might have to change your $PATH.
# export PATH=$HOME/bin:/usr/local/bin:$PATH

# Path to your oh-my-zsh installation.
export ZSH="/$HOME/.oh-my-zsh"

# Set name of the theme to load --- if set to "random", it will
# load a random theme each time oh-my-zsh is loaded, in which case,
# to know which specific one was loaded, run: echo $RANDOM_THEME
# See https://github.com/ohmyzsh/ohmyzsh/wiki/Themes
# ZSH_THEME="powerlevel10k/powerlevel10k"
ZSH_THEME="robbyrussell"

if [ -f "/$HOME/.env.zsh" ]; 
then
  source "/$HOME/.env.zsh"
fi


# Set list of themes to pick from when loading at random
# Setting this variable when ZSH_THEME=random will cause zsh to load
# a theme from this variable instead of looking in $ZSH/themes/
# If set to an empty array, this variable will have no effect.
# ZSH_THEME_RANDOM_CANDIDATES=( "robbyrussell" "agnoster" )

# Uncomment the following line to use case-sensitive completion.
# CASE_SENSITIVE="true"

# Uncomment the following line to use hyphen-insensitive completion.
# Case-sensitive completion must be off. _ and - will be interchangeable.
# HYPHEN_INSENSITIVE="true"

# Uncomment one of the following lines to change the auto-update behavior
# zstyle ':omz:update' mode disabled  # disable automatic updates
# zstyle ':omz:update' mode auto      # update automatically without asking
# zstyle ':omz:update' mode reminder  # just remind me to update when it's time

# Uncomment the following line to change how often to auto-update (in days).
# zstyle ':omz:update' frequency 13

# Uncomment the following line if pasting URLs and other text is messed up.
# DISABLE_MAGIC_FUNCTIONS="true"

# Uncomment the following line to disable colors in ls.
# DISABLE_LS_COLORS="true"

# Uncomment the following line to disable auto-setting terminal title.
# DISABLE_AUTO_TITLE="true"

# Uncomment the following line to enable command auto-correction.
# ENABLE_CORRECTION="true"

# Uncomment the following line to display red dots whilst waiting for completion.
# You can also set it to another string to have that shown instead of the default red dots.
# e.g. COMPLETION_WAITING_DOTS="%F{yellow}waiting...%f"
# Caution: this setting can cause issues with multiline prompts in zsh < 5.7.1 (see #5765)
# COMPLETION_WAITING_DOTS="true"

# Uncomment the following line if you want to disable marking untracked files
# under VCS as dirty. This makes repository status check for large repositories
# much, much faster.
# DISABLE_UNTRACKED_FILES_DIRTY="true"

# Uncomment the following line if you want to change the command execution time
# stamp shown in the history command output.
# You can set one of the optional three formats:
# "mm/dd/yyyy"|"dd.mm.yyyy"|"yyyy-mm-dd"
# or set a custom format using the strftime function format specifications,
# see 'man strftime' for details.
# HIST_STAMPS="mm/dd/yyyy"

# Would you like to use another custom folder than $ZSH/custom?
# ZSH_CUSTOM=/path/to/new-custom-folder

# Which plugins would you like to load?
# Standard plugins can be found in $ZSH/plugins/
# Custom plugins may be added to $ZSH_CUSTOM/plugins/
# Example format: plugins=(rails git textmate ruby lighthouse)
# Add wisely, as too many plugins slow down shell startup.
plugins=(git tmux autojump fzf direnv zsh-autosuggestions zsh-syntax-highlighting forgit fzf-tab eza)
# plugins=(git tmux autojump fzf direnv flutter zsh-autosuggestions zsh-syntax-highlighting forgit)

if [ -n "$RUN_BY_ME" ]; then
  ZSH_TMUX_AUTOSTART=true
fi

fpath+=${ZSH_CUSTOM:-${ZSH:-~/.oh-my-zsh}/custom}/plugins/zsh-completions/src
source $ZSH/oh-my-zsh.sh
# compdef _gnu_generic flutter

# User configuration

# export MANPATH="/usr/local/man:$MANPATH"

# You may need to manually set your language environment
# export LANG=en_US.UTF-8

# Preferred editor for local and remote sessions
# if [[ -n $SSH_CONNECTION ]]; then
#   export EDITOR='vim'
# else
#   export EDITOR='mvim'
# fi

# Compilation flags
# export ARCHFLAGS="-arch x86_64"

# Set personal aliases, overriding those provided by oh-my-zsh libs,
# plugins, and themes. Aliases can be placed here, though oh-my-zsh
# users are encouraged to define aliases within the ZSH_CUSTOM folder.
# For a full list of active aliases, run `alias`.
#
# Example aliases
# alias zshconfig="mate ~/.zshrc"
# alias ohmyzsh="mate ~/.oh-my-zsh"

#source /etc/environment

# The next line updates PATH for the Google Cloud SDK.
# if [ -f "/$HOME/google-cloud-sdk/path.zsh.inc" ]; then . "/$HOME/google-cloud-sdk/path.zsh.inc"; fi

# The next line enables shell command completion for gcloud.
# if [ -f "/$HOME/google-cloud-sdk/completion.zsh.inc" ]; then . "/$HOME/google-cloud-sdk/completion.zsh.inc"; fi

# source <(kubectl completion zsh)
this_path="$HOME/.zshrc"
real_path=$(realpath "$this_path")
dot_dir=$(dirname "$real_path")
export DOT_DIR="$dot_dir"

source "$dot_dir/.functions.zsh"
# source "$dot_dir/.p10k.zsh"
source "$dot_dir/.nnn.zsh"
source "$dot_dir/.autojump.zsh"
source "$dot_dir/.pet.sh"
source "$dot_dir/.scrcpy.zsh"
source "$dot_dir/.fzf.zsh"
source "$dot_dir/.git.zsh"
source "$dot_dir/.forgit.zsh"
source "$dot_dir/.lspconfig.zsh"
source "$dot_dir/.nvm.zsh"
source "$dot_dir/.nvim.zsh"
source "$dot_dir/.tmux.zsh"
source "$dot_dir/.android.zsh"
source "$dot_dir/.luaenv.zsh"
source "$dot_dir/.ranger.zsh"
source "$dot_dir/.goenv.zsh"
source "$dot_dir/.just.zsh"
source "$dot_dir/.ssh.zsh"
source "$dot_dir/.gh.zsh"

export PATH=$DOT_DIR/git:$PATH

# ensure compatibility tmux <-> direnv
if [ -n "$TMUX" ] && [ -n "$DIRENV_DIR" ]; then
    direnv reload
fi

export DISABLE_AUTO_TITLE='true'

if [ -f $HOME/bin ]; then
  export PATH=$HOME/bin:$PATH
fi

export PATH=$JAVA_HOME/bin:$PATH

[ -f $HOME/.config/broot/launcher/bash/br ] && source $HOME/.config/broot/launcher/bash/br

# # Add RVM to PATH for scripting. Make sure this is the last PATH variable change.
[ -f $HOME/.rvm/bin ] && export PATH=$HOME/.rvm/bin:$PATH

[ -f $HOME/.cargo/env ] && source $HOME/.cargo/env

autoload -U compinit && compinit

source "$dot_dir/.pyenv.zsh"
source "$dot_dir/.kompose.zsh"
source "$dot_dir/.kubectl.zsh"
