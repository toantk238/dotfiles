function ranger_wrapper {
    /usr/bin/ranger $*
    local quit_cd_wd_file="$HOME/.cache/ranger/quit_cd_wd"
    if [ -s "$quit_cd_wd_file" ]; then
        cd "$(cat $quit_cd_wd_file)"
        true > "$quit_cd_wd_file"
    fi
}

alias rng='ranger_wrapper'
alias n='ranger_wrapper'
