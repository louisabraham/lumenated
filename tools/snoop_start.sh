#!/usr/bin/env bash
# Enable Bluetooth HCI snoop logging on the phone, then reset the BT stack so
# it starts a fresh log. You then exercise the Lumenate app; run snoop_pull.sh after.
set -euo pipefail

echo "== enabling HCI snoop log (full) =="
adb shell settings put secure bluetooth_hci_log 1 || true
# Some OEMs use a different key; set both.
adb shell settings put global bluetooth_hci_log 1 || true

cat <<'EOF'

Now do this ON THE PHONE (one-time, per OEM):
  Settings > Developer options > "Enable Bluetooth HCI snoop log" -> set to "Enabled" / "Filtered"? choose FULL if offered.
  (On Samsung it's under the same menu; on Pixel it's a toggle.)

Then TOGGLE BLUETOOTH OFF AND ON so a fresh log file is created.

After that, in the Lumenate app:
  1. connect to the Nova
  2. perform ONE action at a time, pausing ~2s between them, and NOTE the order:
       - e.g. turn light on, change brightness up/down, start a session, stop, disconnect
  3. keep a written list of the actions + order (we correlate by timestamp).

When done, run:  tools/snoop_pull.sh
EOF
