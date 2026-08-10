#!/usr/bin/env python3
"""Generate a P-Vector motion CSV compatible with the uploaded examples."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

NUM_MOTORS = 12
NUM_PVECTORS = 20


def fmt(value: float) -> str:
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return text if "." in text else text + ".0"


def pvector(target_deg: float, duration_ms: int, accel: int = 0, decel: int = 0) -> str:
    if not -360 <= target_deg <= 360:
        raise ValueError("target angle must be within -360 to 360 degrees")
    if duration_ms <= 0:
        raise ValueError("duration must be positive")
    if not -128 <= accel <= 128 or not -128 <= decel <= 128:
        raise ValueError("accel/decel must be within -128 to 128")
    return f"{fmt(target_deg)},{duration_ms},{accel},{decel}"


def build_rows(
    slot: int,
    name: str,
    motors: list[int],
    start_deg: float,
    delta_deg: float,
    settle_ms: int,
    move_ms: int,
    hold_ms: int,
    accel: int,
    decel: int,
) -> list[list[str]]:
    if not motors or any(not 0 <= motor < NUM_MOTORS for motor in motors):
        raise ValueError(f"each motor must be 0..{NUM_MOTORS - 1}")
    controlled = set(motors)

    target_deg = start_deg + delta_deg
    if not -360 <= start_deg <= 360 or not -360 <= target_deg <= 360:
        raise ValueError("start and target angles must be within -360 to 360 degrees")

    rows: list[list[str]] = [
        ["robot_id", "1"] + [""] * 21,
        ["file_version", "3.0.0"] + [""] * 21,
        ["MS ID", "MS Name", "MD ID", "P vector"] + [""] * 19,
        ["", "", ""] + [str(i) for i in range(NUM_PVECTORS)],
    ]

    for md in range(NUM_MOTORS):
        pv = ["-"] * NUM_PVECTORS
        if md in controlled:
            index = 0
            if settle_ms > 0:
                pv[index] = pvector(start_deg, settle_ms, 0, 0)
                index += 1
            pv[index] = pvector(target_deg, move_ms, accel, decel)
            index += 1
            if hold_ms > 0:
                pv[index] = pvector(target_deg, hold_ms, 0, 0)

        prefix = [str(slot), name, f"MD{md}"] if md == 0 else ["", "", f"MD{md}"]
        rows.append(prefix + pv)

    assert all(len(row) == 23 for row in rows)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a relative-angle P-Vector motion CSV")
    parser.add_argument("--output", default="motion_04.csv")
    parser.add_argument("--slot", type=int, default=4)
    parser.add_argument("--name", default="ROTATE10_DUAL")
    parser.add_argument(
        "--motor", type=int, action="append", dest="motors",
        help="MD index, 0 through 11; repeat for multiple motors (default: 0 and 1)",
    )
    parser.add_argument("--start", type=float, default=0.0, help="absolute start angle in output-shaft degrees")
    parser.add_argument("--delta", type=float, default=10.0, help="relative angle change in degrees")
    parser.add_argument("--settle-ms", type=int, default=300)
    parser.add_argument("--move-ms", type=int, default=1000)
    parser.add_argument("--hold-ms", type=int, default=1000)
    parser.add_argument("--accel", type=int, default=0)
    parser.add_argument("--decel", type=int, default=0)
    args = parser.parse_args()

    rows = build_rows(
        slot=args.slot,
        name=args.name,
        motors=args.motors or [0, 1],
        start_deg=args.start,
        delta_deg=args.delta,
        settle_ms=args.settle_ms,
        move_ms=args.move_ms,
        hold_ms=args.hold_ms,
        accel=args.accel,
        decel=args.decel,
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="ascii") as f:
        csv.writer(f, lineterminator="\n").writerows(rows)

    print(f"Created {output}")
    labels = ", ".join(f"MD{motor}" for motor in (args.motors or [0, 1]))
    print(f"{labels}: {args.start:.4g} deg -> {args.start + args.delta:.4g} deg in {args.move_ms} ms")


if __name__ == "__main__":
    main()
