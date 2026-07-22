#!/usr/bin/env bash
# Pull the Lumenate app APK(s) from a USB-connected Android phone.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p apk

echo "== adb devices =="
adb devices -l

# Find the package. Lumenate's package id is typically co.lumenate / com.lumenate*.
echo "== searching for lumenate package =="
PKG=$(adb shell pm list packages 2>/dev/null | tr -d '\r' | sed 's/package://' \
      | grep -iE 'lumenate|lumen' | head -1 || true)

if [ -z "${PKG:-}" ]; then
  echo "Could not auto-find the package. All installed 3rd-party packages:"
  adb shell pm list packages -3 2>/dev/null | tr -d '\r' | sed 's/package://' | sort
  echo
  echo "Re-run as: $0 <package.id>"
  [ $# -ge 1 ] && PKG="$1" || exit 1
fi

echo "== package: $PKG =="
# A package can be split into several APKs (base + config splits).
PATHS=$(adb shell pm path "$PKG" | tr -d '\r' | sed 's/package://')
echo "$PATHS"

i=0
for p in $PATHS; do
  out="apk/${PKG}.$i.apk"
  echo "pulling $p -> $out"
  adb pull "$p" "$out"
  i=$((i+1))
done

echo "== done; APKs in ./apk =="
ls -la apk/
