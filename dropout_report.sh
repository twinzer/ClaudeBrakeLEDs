#!/bin/bash
# dropout_report.sh
# Captures everything needed to diagnose a brake LED dropout: recent
# service activity, any crash dumps, and a backtrace if one exists.
# Prints to the terminal (for screenshotting via ConnectBot) and also
# appends to dropout_reports.log as a permanent backup.
#
# Called from ConnectBot's "pedalled-diag" host Post-login automation:
#   bash ~/PedalLEDs/dropout_report.sh

exec > >(tee -a ~/dropout_reports.log) 2>&1

command -v gdb >/dev/null || sudo apt install gdb -y

echo "=== Dropout Report: $(date) ==="
echo ""
echo "--- Recent service activity ---"
sudo journalctl -u pedalleds.service --since "20 minutes ago" --no-pager | grep -E "SEGV|Started|signal|exited"

echo ""
echo "--- Recent crash dumps ---"
sudo coredumpctl list --no-legend | tail -5

echo ""
echo "--- Most recent crash details ---"
sudo coredumpctl info

echo ""
echo "--- Backtrace ---"
COREFILE=/tmp/latest_core
EXEPATH=$(sudo coredumpctl info 2>/dev/null | grep Executable | awk '{print $2}')
sudo coredumpctl dump -o "$COREFILE" 2>&1
if [ -f "$COREFILE" ]; then
    sudo gdb "$EXEPATH" "$COREFILE" -batch -ex "bt"
    sudo rm -f "$COREFILE"
else
    echo "No core file available."
fi

echo ""
echo "=== END REPORT — scroll up and screenshot everything above ==="
