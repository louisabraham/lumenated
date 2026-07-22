#!/usr/bin/env bash
# Decompile the base APK with jadx and surface the BLE-relevant bits.
set -euo pipefail
cd "$(dirname "$0")/.."

APK="${1:-$(ls apk/*.0.apk apk/*.apk 2>/dev/null | head -1)}"
if [ -z "${APK:-}" ] || [ ! -f "$APK" ]; then
  echo "No APK found. Run tools/pull_apk.sh first, or pass an APK path."
  exit 1
fi
echo "== decompiling $APK =="
OUT="apk/decompiled"
rm -rf "$OUT"
# --no-res speeds it up; keep deobf off so names stay readable where possible.
jadx -d "$OUT" "$APK" 2>&1 | tail -5 || echo "(jadx reported errors; sources usually still usable)"

echo
echo "== grep: 128-bit UUIDs =="
grep -rhoE '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}' "$OUT" 2>/dev/null \
  | sort | uniq -c | sort -rn | head -40

echo
echo "== grep: BLE / GATT symbols =="
grep -rliE 'BluetoothGatt|writeCharacteristic|GattCharacteristic|ScanFilter|BluetoothLe|RxBle|nordic|characteristicWrite' "$OUT" 2>/dev/null | head -40

echo
echo "== grep: likely device name / scan filter =="
grep -rhiE '"(nova|lumenate|LUM|glo)[^"]*"' "$OUT" 2>/dev/null | sort -u | head -40
