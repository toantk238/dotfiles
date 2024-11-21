export PATH=$HOME/.pyenv/bin:$PATH
export PYENV_ROOT=$HOME/.pyenv

if exists pyenv; then
  eval "$(pyenv init -)"
  eval "$(pyenv init --path)"
  eval "$(pyenv virtualenv-init -)"
fi
