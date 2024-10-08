#!/usr/bin/env bash

# This script will try to find the adb remote debugging port in the specified
# IP address and then tell adb to try to connect to it.
# It is useful for connecting to an android device without opening the
# "Wireless debugging" screen to get the IP and the random port, which is
# cumbersome.

for line in $(avahi-browse --terminate --resolve --parsable --no-db-lookup _adb-tls-connect._tcp); do
	if [[ $line != =* ]]; then
		continue
	fi

	IFS=';'; fields=($line); unset IFS;
	uri="${fields[7]}:${fields[8]}"

	echo "INFO: it will try to connect on $uri"
	adb_result=$(adb connect $uri)
	echo $adb_result

	# Note: adb exits with 0 even if the connection fails,
	# so I'm checking its output
	if [[ $adb_result =~ connected ]]; then
		echo "INFO: sucefully connected"
		exit 0
	fi
done

echo "ERROR: unable to identify the ADB port on the android device"
exit 1
