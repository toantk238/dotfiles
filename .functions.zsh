function join_by {
  local d=${1-} f=${2-}
  if shift 2; then
    printf %s "$f" "${@/#/$d}"
  fi
}

osis() {
  local n=0
  if [[ "$1" = "-n" ]]; then
    n=1
    shift
  fi

  # echo $OS|grep $1 -i >/dev/null
  uname -s | grep -i "$1" >/dev/null

  return $(($n ^ $?))
}

nvim_edit_config() {
  LAST_FOLDER=$PWD
  CONFIG_FOLDER=$HOME/.config/nvim
  cd $CONFIG_FOLDER
  nvim
  cd $LAST_FOLDER
}

nvim_clear_config() {
  read yn"?Are you sure that you wanna clear ALL neovim configs ? (y/n): "
  case $yn in
  [Yy]*)
    force_clear_nvim_config
    echo "Clear done !"
    ;;
  [Nn]*)
    echo "Cancel !"
    ;;
  *) echo "Please answer yes or no." ;;
  esac
}

function force_clear_nvim_config() {
  rm -rf ~/.cache/nvim
  rm -rf ~/.local/share/nvim
  rm -rf ~/.local/state/nvim
  rm -rf ~/.config/nvim/plugin/*.*
  rm -rf ~/.config/nvim/lazy-lock.json
}

cdl() {
  exe_path=$(which "$1")
  if [[ "$exe_path" == *"not found"* ]]; then
    cd "$(dirname "$(readlink -f "$1")")"
    return 0
  fi

  cd "$(dirname "$(readlink -f "$exe_path")")"
}

nvo() {
  LAST_FOLDER=$PWD
  cd $DOT_DIR
  nvim
  cd $LAST_FOLDER
}

fzf_docker_actions() {

  container=$(docker ps | fzf)
  if [ $? -ne 0 ]; then
    echo "Canceled"
    return 1
  fi
  container_id=$(echo $container | awk '{print $1}')

  all_actions="log\nbash"

  action=$(echo $all_actions | fzf)
  if [ $? -ne 0 ]; then
    echo "Canceled"
    return 1
  fi

  if [ $action = "log" ]; then
    exe_cmd="docker logs -f $container_id"
  elif [ $action = "bash" ]; then
    exe_cmd="docker exec -it $container_id bash"
  fi
  print -s "$exe_cmd"
  eval "$exe_cmd"
}

fzf_k8s_actions() {

  name_space=$(kubectl get ns | fzf)
  if [ $? -ne 0 ]; then
    echo "Canceled"
    return 1
  fi
  name_space=$(echo $name_space | awk '{print $1}')

  pod=$(kubectl get pod -n $name_space | fzf)
  if [ $? -ne 0 ]; then
    echo "Canceled"
    return 1
  fi
  pod=$(echo $pod | awk '{print $1}')

  containers=$(kubectl get pod $pod -n $name_space -o jsonpath='{.spec.containers[*].name}')
  container=$(awk 'NR>0' RS='[[:space:]]' <<<"$containers" | fzf)

  all_actions="log\nbash"

  action=$(echo $all_actions | fzf)
  if [ $? -ne 0 ]; then
    echo "Canceled"
    return 1
  fi

  if [ $action = "log" ]; then
    exe_cmd="kubectl logs -n $name_space -f $pod -c $container"
  elif [ $action = "bash" ]; then
    exe_cmd="kubectl exec -n $name_space -ti $pod -c $container -- bash"
  fi
  print -s "$exe_cmd"
  eval "$exe_cmd"
}

nginx_sites() {
  cd /etc/nginx/sites-available/
}

adb_log_filter() {
  echo '--- Start capture ADB log ---'
  temp="$@"
  command=$(echo "$temp" | sed 's/ *$//g')

  if [ -z "$command" ]; then
    adb logcat -v color
  else
    adb logcat -v color | grep $@
  fi
}

run_in_parent() {
  command="$@"
  exe_file="$1"
  current_d=$PWD
  temp=$PWD

  while [[ true ]]; do
    if [ -f "$temp/$1" ]; then
      $@
      cd $current_d
      return 0
    fi
    cd $temp/..
    temp=$PWD
    if [ "$temp" = "/" ]; then
      echo "Cannot find any place to run this command"
      cd $current_d
      return 1
    fi
  done
}

# handle_docker_compose() {
# 	action="$1"
#
# 	if [ "$action" = "down" ]; then
# 		read yn"?Are you sure that you run DOCKER-COMPOSE DOWN ? (y/n): "
# 		case $yn in
# 		[Yy]*)
# 			/opt/homebrew/bin/docker-compose $@
# 			echo "Running docker-compose down DONE !"
# 			;;
# 		[Nn]*)
# 			echo "Cancel !"
# 			;;
# 		*) echo "Please answer yes or no." ;;
# 		esac
# 		return 0
# 	fi
#
# 	/opt/homebrew/bin/docker-compose $@
# }

exists() {
  command -v "$1" >/dev/null 2>&1
}

cdo() {
  cd $DOT_DIR
}

cptp() {
  output=$(echo "$1")

  (($#)) || set -- -
  while (($#)); do
    # { [[ $1 = - ]] || exec < "$1"; } &&
    while read -r; do
      input_file=$(echo "$REPLY")
      output_file="$output/$input_file"
      output_file_dir=$(dirname $output_file)
      mkdir -p $output_file_dir && cp -r $input_file "$output_file_dir/."
    done
    shift
  done
}

lnr() {
  ln -s "$(realpath $1)" $2
}

export LC_ALL="en_US.UTF-8"

if exists eza; then
  alias l="eza -lah --icons=auto"
  alias lt="eza -lah --icons=auto --tree"
  alias ltg="eza -lah --icons=auto --tree --git-ignore"
fi

if exists fuck; then
  eval $(thefuck --alias)
fi

if exists kitty && [[ -z "$SSH_CONNECTION" ]]; then
  alias ssh="kitty +kitten ssh"
fi

if exists kitty; then
  alias icat="kitten icat"
fi


if exists bat; then
  alias cat="bat --paging=never -p"
  export MANPAGER="sh -c 'col -bx | bat -l man -p'"
  export MANROFFOPT="-c"
fi

if exists btop; then
  alias top="btop"
fi

if exists glow; then
  eval "$(glow completion zsh)"
  alias glow="glow --pager"
fi

if exists cloudlens; then
  alias cloudlens="cloudlens aws"
fi

if exists lazydocker; then
  alias lzd="lazydocker"
fi

alias gdiff="yes | git difftool --tool=intelliJ HEAD"
alias ssys="sudo systemctl"
# alias n="nnn"
alias ncp="cat ${NNN_SEL:-${XDG_CONFIG_HOME:-$HOME/.config}/nnn/.selection} | tr '\0' '\n'"
alias nv="nvim"
# alias docker-compose="handle_docker_compose"
alias lc="lemonade copy --host=127.0.0.1"
# alias glow="glow --pager"
if exists xdg-open; then
  alias open="xdg-open"
fi
alias enw="emacs -nw"
alias duhs="du -hs"
alias sudoe="sudo -E"

# Use du only with top level, and size is sorted as increasing
dur() {
  du -ah $@ --max-depth=0 | sort -h
}

osis Darwin && {
  dur() {
    du -h -d 0 $@ | sort -h
  }
}
alias gcurl='curl -H "Authorization: Bearer $(gcloud auth print-access-token)" -H "Content-Type: application/json"'

if [[ -f /usr/bin/src-hilite-lesspipe.sh ]]; then
  export LESSOPEN="| /usr/bin/src-hilite-lesspipe.sh %s"
  export LESS=' -R'
elif exists moor; then
  export PAGER=$(which moor)
  export MOAR='--statusbar=bold --no-linenumbers'
  alias less="$PAGER"
else
  export PAGER='less -R'
fi

apk_key_hash() {
  keytool -exportcert -alias $1 -keystore $2 | openssl sha256 -binary | openssl base64 | sed 's/=//g' | sed s/\\+/-/g | sed s/\\//_/g | sed -E s/=+$//
}

osis Darwin && {
  lctl() {
    if [[ "$1" == "reload" ]]; then
      launchctl unload -w $2
      launchctl load -w $2
    elif [[ "$1" == "load" ]]; then
      launchctl load -w $2
    elif [[ "$1" == "unload" ]]; then
      echo "run stop"
      launchctl unload -w $2
    fi
  }
}

# # if lsd, replace ls
# if exists lsd; then
#   alias ls="lsd"
#   alias l="ls -Al;"
#   alias lt="ls --tree"
# fi
#

ssh_tmux() {
  if [ -n "$SSH_CLIENT" ] || [ -n "$SSH_TTY" ]; then       # if this is an SSH session
    if which tmux >/dev/null 2>&1; then                    # check if tmux is installed
      if [[ -z "$TMUX" ]]; then                            # do not allow "tmux in tmux"
        ID="$(tmux ls | grep -vm1 attached | cut -d: -f1)" # get the id of a deattached session
        if [[ -z "$ID" ]]; then                            # if not available create a new one
          tmux new-session
        else
          tmux attach-session -t "$ID" # if available, attach to it
        fi
      fi
    fi
  fi
}
