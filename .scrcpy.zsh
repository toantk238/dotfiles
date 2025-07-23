#!/bin/zsh

mount_adb() {
  ssh -i ~/.ssh/rock_rsa -CN -L5038:127.0.0.1:5037 -L27183:localhost:27183 mbhealth@192.168.100.62
}

# if there is port 5038 is in used, export the below
PORT=5038

if lsof -iTCP:$PORT -sTCP:LISTEN -t >/dev/null; then
  alias scrcpy_adb_forward="scrcpy -m 900 --force-adb-forward"
  export ANDROID_ADB_SERVER_PORT=5038
  export ADB_SERVER_SOCKET=tcp:localhost:5038
  # echo "Port $PORT is in use."
else
  # echo "Port $PORT is available."
fi


function start_new_device() {
	device_serial="$1"
	(tmux kill-session -t "scrcpy-$device_serial" | true) && tmux new-session -d -s "scrcpy-$device_serial" "scrcpy -s $device_serial -m 800 --no-audio" && echo "Start scrcpy with device $device_serial"
}

function scrcpy_all() {
	IFS=$'\n' all_devices=($(adb devices | grep -v devices))

	for line in $all_devices; do
		device_serial=$(echo "$line" | awk '{print $1}')
		start_new_device $device_serial
	done
}
