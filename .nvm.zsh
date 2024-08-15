# [ -f /usr/share/nvm/init-nvm.sh ] && source /usr/share/nvm/init-nvm.sh
[ -z "$NVM_DIR" ] && export NVM_DIR="$HOME/.nvm"
[ -f "$NVM_DIR/nvm.sh" ] && source $NVM_DIR/nvm.sh
# [ -f /usr/share/nvm/nvm.sh ] && source /usr/share/nvm/nvm.sh
# [ -f /usr/share/nvm/bash_completion ] && source /usr/share/nvm/bash_completion
# [ -f /usr/share/nvm/install-nvm-exec ] && source /usr/share/nvm/install-nvm-exec
[ -s "/opt/homebrew/opt/nvm/nvm.sh" ] && \. "/opt/homebrew/opt/nvm/nvm.sh"  # This loads nvm
[ -s "/opt/homebrew/opt/nvm/etc/bash_completion.d/nvm" ] && \. "/opt/homebrew/opt/nvm/etc/bash_completion.d/nvm"  # This loads nvm bash_completion
