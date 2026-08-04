#!/bin/bash
# shutdown_both.sh
# Shuts down the Beelink (BL) first via outbound SSH, then shuts down
# this Pi. Order matters — the Pi can't do anything useful after it
# powers itself off, so the remote shutdown must happen first.
#
# Called from ConnectBot's "pedalled" host Post-login automation:
#   bash ~/PedalLEDs/shutdown_both.sh

ssh -f -o ConnectTimeout=5 me@10.0.0.82 "sudo shutdown now"
sleep 5
sudo shutdown now
