#!/usr/bin/env python3
"""Patch the 2026-08-06 arm64 phorce_monitor powered-axis guard for motor ID 0x02.

Motor IDs are encoded as bit (id - 2), so ID 0x02 uses mask 0x0001.
The distributed binary compares the command-mode mask against 0x0002 (ID 0x03).
This patch changes only that AArch64 CMP immediate and verifies the input build ID.
"""

from pathlib import Path
import hashlib
import sys


EXPECTED_SHA256 = "b84aa4c52fa0561c0d77ada50e8f353d570131af9d714c53fb15dbeb9f241815"
OFFSET = 0x1C350
OLD = bytes.fromhex("1f0800f1")  # cmp x0, #2
NEW = bytes.fromhex("1f0400f1")  # cmp x0, #1


def main() -> int:
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} INPUT OUTPUT", file=sys.stderr)
        return 2
    source, target = map(Path, sys.argv[1:])
    data = bytearray(source.read_bytes())
    digest = hashlib.sha256(data).hexdigest()
    if digest != EXPECTED_SHA256:
        raise SystemExit(f"unexpected input sha256: {digest}")
    if data[OFFSET : OFFSET + 4] != OLD:
        raise SystemExit(f"unexpected instruction at 0x{OFFSET:x}")
    data[OFFSET : OFFSET + 4] = NEW
    target.write_bytes(data)
    target.chmod(0o755)
    print(hashlib.sha256(data).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
