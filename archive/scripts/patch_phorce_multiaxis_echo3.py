#!/usr/bin/env python3
"""Build a narrowly patched PhORCE monitor for the observed six-axis PCM.

Changes:
  * command-mode powered-axis contract: 0x0002 -> 0x01c7
  * displayed expected mask:             0x0002 -> 0x01c7
  * tolerated command-echo lag:          2 cycles -> 3 cycles

All other safety checks, including the lag strike/window budget, are retained.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path


SOURCE = Path("/opt/ros/humble/lib/agx_phorce_bridge/phorce_monitor")
DEST = Path("/home/phorce/.local/lib/phorce-mask01c7-echo3/phorce_monitor")
EXPECTED_SHA256 = "b84aa4c52fa0561c0d77ada50e8f353d570131af9d714c53fb15dbeb9f241815"

PATCHES = (
    (0x1C350, bytes.fromhex("1f0800f1"), bytes.fromhex("1f1c07f1"), "axis-mask compare"),
    (0x1C7E8, bytes.fromhex("44008052"), bytes.fromhex("e4388052"), "expected-mask diagnostic"),
    (0x7330C, bytes.fromhex("1f080071"), bytes.fromhex("1f0c0071"), "echo-lag maximum"),
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    data = bytearray(SOURCE.read_bytes())
    actual = digest(data)
    if actual != EXPECTED_SHA256:
        raise SystemExit(f"refusing unknown source binary: sha256={actual}")

    for offset, old, new, label in PATCHES:
        found = bytes(data[offset : offset + len(old)])
        if found != old:
            raise SystemExit(
                f"{label}: offset 0x{offset:x}: expected {old.hex()}, found {found.hex()}"
            )
        data[offset : offset + len(old)] = new

    DEST.parent.mkdir(parents=True, exist_ok=True)
    tmp = DEST.with_suffix(".tmp")
    tmp.write_bytes(data)
    os.chmod(tmp, 0o755)
    tmp.replace(DEST)
    print(f"created {DEST}")
    print(f"sha256 {digest(data)}")


if __name__ == "__main__":
    main()
