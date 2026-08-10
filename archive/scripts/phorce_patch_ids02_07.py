#!/usr/bin/env python3
"""Patch the arm64 monitor for six motors with CAN IDs 0x02 through 0x07."""

from pathlib import Path
import hashlib
import sys


EXPECTED_SHA256 = "b84aa4c52fa0561c0d77ada50e8f353d570131af9d714c53fb15dbeb9f241815"
PATCHES = (
    # command-mode powered mask guard: cmp x0, #2 -> cmp x0, #0x3f
    (0x1C350, bytes.fromhex("1f0800f1"), bytes.fromhex("1ffc00f1")),
    # fatal-message format argument: mov w4, #2 -> mov w4, #0x3f
    (0x1C7E8, bytes.fromhex("44008052"), bytes.fromhex("e4078052")),
)


def main() -> int:
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} INPUT OUTPUT", file=sys.stderr)
        return 2
    source, target = map(Path, sys.argv[1:])
    data = bytearray(source.read_bytes())
    digest = hashlib.sha256(data).hexdigest()
    if digest != EXPECTED_SHA256:
        raise SystemExit(f"unexpected input sha256: {digest}")
    for offset, old, new in PATCHES:
        if data[offset : offset + len(old)] != old:
            raise SystemExit(f"unexpected instruction at 0x{offset:x}")
        data[offset : offset + len(old)] = new
    target.write_bytes(data)
    target.chmod(0o755)
    print(hashlib.sha256(data).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
