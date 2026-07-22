#!/usr/bin/env python3
"""Extract GATT-layer activity from an HCI btsnoop log using tshark.

Shows ATT writes, notifications, and handle/UUID mappings in time order so we
can correlate app actions with the bytes on the wire.

Usage:
    python3 tools/analyze_snoop.py captures/btsnoop-XXXX.log
"""
import subprocess
import sys


def run(args):
    return subprocess.run(args, capture_output=True, text=True).stdout


def main(path):
    # 1) Handle <-> UUID discovery (from the read-by-type / find-info responses)
    print("=== ATT handle/UUID map (from discovery) ===")
    out = run([
        "tshark", "-r", path, "-Y",
        "btatt.uuid16 || btatt.uuid128",
        "-T", "fields",
        "-e", "btatt.handle", "-e", "btatt.uuid16", "-e", "btatt.uuid128",
    ])
    seen = set()
    for line in out.splitlines():
        if line.strip() and line not in seen:
            seen.add(line)
            print(" ", line)

    # 2) All ATT PDUs with values, in time order
    print("\n=== ATT operations (time-ordered) ===")
    out = run([
        "tshark", "-r", path,
        "-Y", "btatt",
        "-T", "fields",
        "-e", "frame.time_relative",
        "-e", "btatt.opcode",
        "-e", "btatt.handle",
        "-e", "btatt.value",
        "-E", "separator=\t",
    ])
    for line in out.splitlines():
        if line.strip():
            print(" ", line)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1])
