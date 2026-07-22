#!/usr/bin/env bash
# Retrieve the Bluetooth HCI snoop log from the phone by dumping a bugreport
# (works without root on modern Android) and extracting the btsnoop file.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p captures

TS=$(date +%Y%m%d-%H%M%S)

# 1) Try the well-known direct paths first (needs permission; usually blocked without root).
for p in \
  /data/misc/bluetooth/logs/btsnoop_hci.log \
  /sdcard/btsnoop_hci.log \
  /sdcard/Android/data/btsnoop_hci.log ; do
  if adb pull "$p" "captures/btsnoop-$TS.log" 2>/dev/null; then
    echo "pulled $p"
    exit 0
  fi
done

echo "Direct pull failed (expected without root). Falling back to bugreport..."
# 2) bugreport contains FS/btsnoop_hci.log inside the zip on most devices.
adb bugreport "captures/bugreport-$TS.zip"
echo "== extracting btsnoop from bugreport =="
python3 - "$TS" <<'PY'
import sys, zipfile, os, glob
ts = sys.argv[1]
zips = sorted(glob.glob(f"captures/bugreport-{ts}*.zip"))
if not zips:
    zips = sorted(glob.glob("captures/bugreport-*.zip"))
z = zips[-1]
found = []
with zipfile.ZipFile(z) as zf:
    for n in zf.namelist():
        if "btsnoop" in n.lower() or n.lower().endswith(".cfa"):
            data = zf.read(n)
            out = f"captures/btsnoop-{ts}.log"
            with open(out, "wb") as f:
                f.write(data)
            found.append((n, out, len(data)))
if found:
    for n, out, sz in found:
        print(f"extracted {n} -> {out} ({sz} bytes)")
else:
    print("No btsnoop file inside the bugreport. Names containing 'bt':")
    with zipfile.ZipFile(z) as zf:
        for n in zf.namelist():
            if "bt" in n.lower():
                print("  ", n)
PY
