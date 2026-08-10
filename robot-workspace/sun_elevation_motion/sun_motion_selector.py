#!/usr/bin/env python3
"""대전의 현재 태양 고도로 모션 슬롯을 선택한다.

기본 실행은 계산과 선택 결과만 출력한다. 실제 로봇을 움직이려면
명시적으로 ``--enable-motion``을 붙여야 한다.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class SunPosition:
    azimuth_deg: float
    elevation_deg: float


def solar_position(when: datetime, latitude_deg: float, longitude_deg: float) -> SunPosition:
    """NOAA fractional-year 근사식으로 태양 방위각/고도를 계산한다."""
    if when.tzinfo is None or when.utcoffset() is None:
        raise ValueError("when must be timezone-aware")

    day = when.timetuple().tm_yday
    hour = when.hour + when.minute / 60.0 + when.second / 3600.0
    days_in_year = 366 if when.year % 4 == 0 and (when.year % 100 != 0 or when.year % 400 == 0) else 365
    gamma = 2.0 * math.pi / days_in_year * (day - 1 + (hour - 12.0) / 24.0)

    equation_of_time = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2.0 * gamma)
        - 0.040849 * math.sin(2.0 * gamma)
    )
    declination = (
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2.0 * gamma)
        + 0.000907 * math.sin(2.0 * gamma)
        - 0.002697 * math.cos(3.0 * gamma)
        + 0.00148 * math.sin(3.0 * gamma)
    )

    timezone_hours = when.utcoffset().total_seconds() / 3600.0
    solar_minutes = (
        hour * 60.0 + equation_of_time + 4.0 * longitude_deg - 60.0 * timezone_hours
    ) % 1440.0
    hour_angle = math.radians(solar_minutes / 4.0 - 180.0)
    latitude = math.radians(latitude_deg)

    cos_zenith = (
        math.sin(latitude) * math.sin(declination)
        + math.cos(latitude) * math.cos(declination) * math.cos(hour_angle)
    )
    zenith = math.acos(max(-1.0, min(1.0, cos_zenith)))
    elevation = 90.0 - math.degrees(zenith)
    azimuth = (
        math.degrees(
            math.atan2(
                math.sin(hour_angle),
                math.cos(hour_angle) * math.sin(latitude)
                - math.tan(declination) * math.cos(latitude),
            )
        )
        + 180.0
    ) % 360.0
    return SunPosition(azimuth, elevation)


def select_motion(elevation_deg: float, motions: list[dict[str, Any]]) -> dict[str, Any] | None:
    """min <= 고도 < max인 첫 설정을 반환한다."""
    for motion in motions:
        if float(motion["min_elevation_deg"]) <= elevation_deg < float(motion["max_elevation_deg"]):
            return motion
    return None


def load_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def play_motion(motion_id: int) -> None:
    """로봇에 이미 적재된 모션 슬롯 하나를 재생하고 완료까지 기다린다."""
    try:
        import phorce
    except ImportError as error:
        raise RuntimeError("phorce Python 패키지를 찾을 수 없습니다") from error

    with phorce.connect() as robot:
        report = robot.doctor()
        if not report.ok:
            raise RuntimeError(f"phorce doctor 실패: {report.issues}")
        result = robot.play(motion_id)
        if not result.ok:
            raise RuntimeError(f"motion {motion_id} 실행 실패: {result.detail}")


def parse_args() -> argparse.Namespace:
    default_config = Path(__file__).with_name("config.json")
    parser = argparse.ArgumentParser(description="현재 태양 고도로 실행할 모션 선택")
    parser.add_argument("--config", type=Path, default=default_config)
    parser.add_argument("--at", help="테스트용 현지 시각 (예: 2026-08-07T14:30:00)")
    parser.add_argument("--enable-motion", action="store_true", help="선택한 모션을 실제 로봇에서 실행")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    location = config["location"]
    timezone = ZoneInfo(location["timezone"])
    when = datetime.fromisoformat(args.at).replace(tzinfo=timezone) if args.at else datetime.now(timezone)
    sun = solar_position(when, float(location["latitude_deg"]), float(location["longitude_deg"]))
    selected = select_motion(sun.elevation_deg, config["motions"])

    print(f"time: {when.isoformat(timespec='seconds')}")
    print(f"sun: azimuth={sun.azimuth_deg:.2f} deg, elevation={sun.elevation_deg:.2f} deg")
    if selected is None:
        print("selected: 없음 (현재 고도에 해당하는 구간이 없습니다)")
        return

    print(
        f"selected: {selected['name']} | motion_id={selected.get('motion_id')} "
        f"| file={selected.get('motion_file')}"
    )
    motion_id = selected.get("motion_id")
    if not args.enable_motion:
        print("dry-run: 실제 실행 안 함 (--enable-motion을 붙이면 실행)")
    elif motion_id is None:
        print("skip: 아직 motion_id가 지정되지 않았습니다")
    else:
        play_motion(int(motion_id))
        print(f"done: motion {motion_id}")


if __name__ == "__main__":
    main()
