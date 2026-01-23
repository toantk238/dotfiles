#!/usr/bin/env zsh

ssh -i ~/.ssh/rock_rsa -CN -L5037:127.0.0.1:5037 -L27183:localhost:27183 mbhealth@192.168.100.62
