nvim_edit_config ()
{
  LAST_FOLDER=$PWD
  CONFIG_FOLDER=$HOME/.config/nvim/lua/custom/
  cd $CONFIG_FOLDER
  nvim .
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


cdl () {
    exe_path=$(which "$1")
    if [[ "$exe_path" == *"not found"* ]]; then
      cd "$(dirname "$(readlink "$1")")"
      return 0
    fi

    cd "$(dirname "$(readlink -f "$exe_path")")"; 
}


k8s_logs () {
  kubectl logs -n $1 -f $(kubectl get pod -n $1 | grep $2 | awk '{print $1}')
}

k8s_bash () {
  kubectl exec -n $1 -ti $(kubectl get pod -n $1 | grep $2 | awk '{print $1}')  -- bash
}

docker_bash() {
  docker exec -it "$(docker ps -qf "name=$1")" bash
}

k8s_fzf_actions () {
  
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
