export ANDROID_SDK=$ANDROID_HOME
export CLOUDSDK_PYTHON=/$HOME/.pyenv/shims/python

export PATH=$ANDROID_HOME/platform-tools:$PATH
export PATH=$ANDROID_HOME/tools:$PATH
export PATH=$ANDROID_HOME/cmdline-tools/latest/bin:$PATH
export PATH=$ANDROID_HOME/emulator:$PATH

adba() {
	IFS=$'\n' all_devices=($(adb devices | grep -v devices))
  devices=()
	for line in $all_devices; do
		device_serial=$(echo "$line" | awk '{print $1}')
    input_cli=$(echo "$@")
    devices+=("adb -s $device_serial $input_cli")
	done

  full_cmd=$(join_by ' & ' $devices)
  echo "full_cmd=$full_cmd"
  eval $full_cmd
  wait
}
