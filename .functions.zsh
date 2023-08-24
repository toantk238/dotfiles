nvim_edit_config ()
{
  LAST_FOLDER=$PWD
  CONFIG_FOLDER=$HOME/.config/nvim
  cd $CONFIG_FOLDER
  nvim
  cd $LAST_FOLDER
}

nvim_clear_config ()
{
  read yn"?Are you sure that you wanna clear ALL neovim configs ? (y/n): "
  case $yn in
    [Yy]* )
      force_clear_nvim_config
      echo "Clear done !"
      ;;
    [Nn]* )
      echo "Cancel !"
      ;;
    *) echo "Please answer yes or no.";;
  esac
}

function force_clear_nvim_config(){
  rm -rf ~/.cache/nvim
  rm -rf ~/.local/share/nvim
  rm -rf ~/.local/state/nvim
  rm -rf ~/.config/nvim/plugin/*.*
}

appium_start ()
{
  PROJECT_DIR="/mnt/Data/Workspace/2.Personal/appium2"
  cd $PROJECT_DIR
  appium server -p 4723 -a 127.0.0.1 -pa /wd/hub
}

alias gdiff="yes | git difftool --tool=intelliJ HEAD"
alias ssys="sudo systemctl"
alias lg="lazygit"
alias cat="bat"
# alias n="nnn"
alias ncp="cat ${NNN_SEL:-${XDG_CONFIG_HOME:-$HOME/.config}/nnn/.selection} | tr '\0' '\n'"
alias kts="kitty +kitten"
alias nv="nvim"
alias icat="kitty +kitten icat"


cdl () {
    exe_path=$(which "$1")
    if [[ "$exe_path" == *"not found"* ]]; then
      cd "$(dirname "$(readlink -f "$1")")"
      return 0
    fi

    cd "$(dirname "$(readlink -f "$exe_path")")"; 
}

fzf_docker_actions () {
  
  container=$(docker ps | fzf)
  if [ $? -ne 0 ]
  then
    echo "Canceled"
    return 1
  fi
  container_id=$(echo $container | awk '{print $1}')
  
  all_actions="log\nbash"
  
  action=$(echo $all_actions | fzf)
  if [ $? -ne 0 ]
  then
    echo "Canceled"
    return 1
  fi

  if [ $action = "log" ] ; then
    docker logs -f $container_id
  elif [ $action = "bash" ] ; then
    docker exec -it $container_id bash
  fi
}

fzf_k8s_actions () {
  
  name_space=$(kubectl get ns | fzf)
  if [ $? -ne 0 ]
  then
    echo "Canceled"
    return 1
  fi
  name_space=$(echo $name_space | awk '{print $1}')
  
  pod=$(kubectl get pod -n $name_space | fzf)
  if [ $? -ne 0 ]
  then
    echo "Canceled"
    return 1
  fi
  pod=$(echo $pod | awk '{print $1}')
  
  all_actions="log\nbash"
  
  action=$(echo $all_actions | fzf)
  if [ $? -ne 0 ]
  then
    echo "Canceled"
    return 1
  fi

  if [ $action = "log" ] ; then
    kubectl logs -n $name_space -f $pod
  elif [ $action = "bash" ] ; then
    kubectl exec -n $name_space -ti $pod -- bash
  fi
}

nginx_sites () {
  cd /etc/nginx/sites-available/
}

adb_log_filter () {
  echo '--- Start capture ADB log ---'
  temp="$@"
  command=$(echo "$temp" | sed 's/ *$//g')
  
  if [ -z "$command" ]; then
    adb logcat -v color
  else
    adb logcat -v color | grep $@
  fi
}

run_in_parent () {
  command="$@"
  exe_file="$1"
  current_d=$PWD
  temp=$PWD

  while [[ true ]]; do
    if [ -f "$temp/$1" ] ; then
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

exists()
{
  command -v "$1" >/dev/null 2>&1
}

export FZF_DEFAULT_COMMAND="fd --type f -HI --exclude .git --exclude .gradle --exclude .transforms --exclude .idea"
#export FZF_DEFAULT_COMMAND="rg --no-ignore --hidden --files -g '!.git/' "
