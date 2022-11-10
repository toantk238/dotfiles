nvim_edit_config ()
{
  CONFIG_FOLDER=$HOME/.config/nvim
  cd $CONFIG_FOLDER
  nvim .
}

appium_start ()
{
  PROJECT_DIR="/mnt/Data/Workspace/2.Personal/appium2"
  cd $PROJECT_DIR
  appium server -p 4723 -a 127.0.0.1 -pa /wd/hub
}

alias gdiff="git difftool --tool=nvimdiff HEAD"
