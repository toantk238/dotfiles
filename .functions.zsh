function join_by {
	local d=${1-} f=${2-}
	if shift 2; then
		printf %s "$f" "${@/#/$d}"
	fi
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

appium_start() {
	PROJECT_DIR="/mnt/Data/Workspace/2.Personal/appium2"
	cd $PROJECT_DIR
	appium server -p 4723 -a 127.0.0.1 -pa /wd/hub
}

alias gdiff="yes | git difftool --tool=intelliJ HEAD"
alias ssys="sudo systemctl"
alias lg="lazygit"
alias cat="bat --paging=never"
# alias n="nnn"
alias ncp="cat ${NNN_SEL:-${XDG_CONFIG_HOME:-$HOME/.config}/nnn/.selection} | tr '\0' '\n'"
alias ssh="kitty +kitten ssh"
alias nv="nvim"
alias icat="kitty +kitten icat"
alias docker-compose="handle_docker_compose"
alias lc="lemonade copy"
alias top="btop"
alias glow="glow --pager"
alias open="xdg-open"

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

handle_docker_compose() {
	action="$1"

	if [ "$action" = "down" ]; then
		read yn"?Are you sure that you run DOCKER-COMPOSE DOWN ? (y/n): "
		case $yn in
		[Yy]*)
			/usr/local/bin/docker-compose $@
			echo "Running docker-compose down DONE !"
			;;
		[Nn]*)
			echo "Cancel !"
			;;
		*) echo "Please answer yes or no." ;;
		esac
		return 0
	fi

	/usr/local/bin/docker-compose $@
}

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

export LC_ALL="en_US.UTF-8"
