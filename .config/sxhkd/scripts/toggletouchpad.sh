	#!/bin/bash
#
# type cmd `xinput`, it shows my device X input information as follow
#
# ➜  ~ xinput
# ⎡ Virtual core pointer                      id=2    [master pointer  (3)]
# ⎜   ↳ Virtual core XTEST pointer                id=4    [slave  pointer  (2)]
# ⎜   ↳ ETPS/2 Elantech Touchpad                  id=14   [slave  pointer  (2)]
# ⎣ Virtual core keyboard                     id=3    [master keyboard (2)]
#     ↳ Virtual core XTEST keyboard               id=5    [slave  keyboard (3)]
#     ↳ Power Button                              id=6    [slave  keyboard (3)]
#     ↳ Asus Wireless Radio Control               id=7    [slave  keyboard (3)]
#     ↳ Video Bus                                 id=8    [slave  keyboard (3)]
#     ↳ Video Bus                                 id=9    [slave  keyboard (3)]
#     ↳ Sleep Button                              id=10   [slave  keyboard (3)]
#     ↳ ASUS USB2.0 Webcam                        id=11   [slave  keyboard (3)]
#     ↳ Asus WMI hotkeys                          id=12   [slave  keyboard (3)]
#     ↳ AT Translated Set 2 keyboard              id=13   [slave  keyboard (3)]
#
# So my touchpad's ID is 14, then use `xinput disable 14` and `xinput enable 14` for toggling~
#
# Following bash script is referred to this askubuntu question:
# http://askubuntu.com/questions/751413/how-to-disable-enable-toggle-touchpad-in-a-dell-laptop

MY_TP_ID=11
if xinput list-props $MY_TP_ID | grep "Device Enabled (148):.*1" >/dev/null
then
    xinput disable $MY_TP_ID
    notify-send -u low -i mouse "Trackpad disabled"
else
    xinput enable $MY_TP_ID
    notify-send -u low -i mouse "Trackpad enabled"
fi
