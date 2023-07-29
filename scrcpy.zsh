#!/bin/zsh

function start_new_device() {
  device_serial="$1"
  (tmux kill-session -t "scrcpy-$device_serial" | true ) && tmux new-session -d -s "scrcpy-$device_serial" "scrcpy -s $device_serial -m 1000 --no-audio"
}

function scrcpy_all () {
  IFS=$'\n' all_devices=($(adb devices | grep -v devices))
  
  for line in $all_devices; do
    device_serial=$(echo "$line" | awk '{print $1}')
    start_new_device $device_serial
  done
}

