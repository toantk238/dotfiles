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

alias gdiff="yes | git difftool --tool=meld HEAD"
alias ss="sudo systemctl"
