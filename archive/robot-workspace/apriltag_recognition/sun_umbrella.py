#!/usr/bin/env python3
"""현재 위치와 시각으로 2축 우산의 안전한 pan/tilt 목표를 계산한다.

좌표 규약
---------
* 태양 방위각: 진북 0도, 동 90도, 남 180도, 서 270도
* robot_heading_deg: 같은 진북 기준의 로봇 정면
* pan: 로봇 정면 0도, 오른쪽 양수
* tilt: 우산 법선이 수직이면 0도, 태양 쪽으로 기울수록 양수

이 모듈은 목표만 계산한다. phorce에서 사용하려면 PAN_LEFT/PAN_RIGHT 및
TILT_UP/TILT_DOWN처럼 축별로 독립된 짧은 모션 슬롯이 필요하다.
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def wrap_180(angle_deg: float) -> float:
    return (angle_deg + 180.0) % 360.0 - 180.0


@dataclass(frozen=True)
class SunPosition:
    azimuth_deg: float
    elevation_deg: float


@dataclass(frozen=True)
class UmbrellaCommand:
    mode: str
    sun: SunPosition
    target_pan_deg: float
    target_tilt_deg: float
    pan_step_deg: float
    tilt_step_deg: float
    reason: str


@dataclass(frozen=True)
class UmbrellaLimits:
    min_sun_elevation_deg: float = 5.0
    max_tilt_deg: float = 35.0
    min_pan_deg: float = -90.0
    max_pan_deg: float = 90.0
    deadband_deg: float = 2.0
    max_step_deg: float = 5.0
    park_pan_deg: float = 0.0
    park_tilt_deg: float = 0.0
    wind_park_m_s: float = 8.0


def solar_position(when: datetime, latitude_deg: float, longitude_deg: float) -> SunPosition:
    """NOAA의 fractional-year 근사식으로 태양 방위각과 고도각을 계산한다.

    ``when``은 timezone-aware여야 한다. 태양 추적에는 시스템 시각 동기화가 필요하다.
    """
    if when.tzinfo is None or when.utcoffset() is None:
        raise ValueError("when must be timezone-aware")
    if not -90.0 <= latitude_deg <= 90.0:
        raise ValueError("latitude must be within -90..90 degrees")
    if not -180.0 <= longitude_deg <= 180.0:
        raise ValueError("longitude must be within -180..180 degrees")

    day = when.timetuple().tm_yday
    hour = when.hour + when.minute / 60.0 + when.second / 3600.0
    days_in_year = 366 if _is_leap_year(when.year) else 365
    gamma = 2.0 * math.pi / days_in_year * (day - 1 + (hour - 12.0) / 24.0)

    equation_of_time_min = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2.0 * gamma)
        - 0.040849 * math.sin(2.0 * gamma)
    )
    declination_rad = (
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2.0 * gamma)
        + 0.000907 * math.sin(2.0 * gamma)
        - 0.002697 * math.cos(3.0 * gamma)
        + 0.00148 * math.sin(3.0 * gamma)
    )

    timezone_hours = when.utcoffset().total_seconds() / 3600.0
    local_minutes = hour * 60.0
    true_solar_minutes = (
        local_minutes + equation_of_time_min + 4.0 * longitude_deg - 60.0 * timezone_hours
    ) % 1440.0
    hour_angle_deg = true_solar_minutes / 4.0 - 180.0
    latitude_rad = math.radians(latitude_deg)
    hour_angle_rad = math.radians(hour_angle_deg)

    cos_zenith = (
        math.sin(latitude_rad) * math.sin(declination_rad)
        + math.cos(latitude_rad) * math.cos(declination_rad) * math.cos(hour_angle_rad)
    )
    zenith_rad = math.acos(clamp(cos_zenith, -1.0, 1.0))
    elevation_deg = 90.0 - math.degrees(zenith_rad)

    azimuth_deg = (
        math.degrees(
            math.atan2(
                math.sin(hour_angle_rad),
                math.cos(hour_angle_rad) * math.sin(latitude_rad)
                - math.tan(declination_rad) * math.cos(latitude_rad),
            )
        )
        + 180.0
    ) % 360.0
    return SunPosition(azimuth_deg, elevation_deg)


def _is_leap_year(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _bounded_step(error_deg: float, limits: UmbrellaLimits) -> float:
    if abs(error_deg) <= limits.deadband_deg:
        return 0.0
    return clamp(error_deg, -limits.max_step_deg, limits.max_step_deg)


def plan_umbrella(
    sun: SunPosition,
    robot_heading_deg: float,
    current_pan_deg: float,
    current_tilt_deg: float,
    limits: UmbrellaLimits = UmbrellaLimits(),
    wind_m_s: Optional[float] = None,
) -> UmbrellaCommand:
    """태양을 향한 목표와 이번 제어 주기에 허용할 작은 보정량을 반환한다."""
    if wind_m_s is not None and wind_m_s >= limits.wind_park_m_s:
        mode = "PARK"
        target_pan = limits.park_pan_deg
        target_tilt = limits.park_tilt_deg
        reason = f"wind {wind_m_s:.1f}m/s >= {limits.wind_park_m_s:.1f}m/s"
    elif sun.elevation_deg <= limits.min_sun_elevation_deg:
        mode = "PARK"
        target_pan = limits.park_pan_deg
        target_tilt = limits.park_tilt_deg
        reason = f"sun elevation {sun.elevation_deg:.1f}deg is too low"
    else:
        mode = "TRACK"
        relative_azimuth = wrap_180(sun.azimuth_deg - robot_heading_deg)
        target_pan = clamp(relative_azimuth, limits.min_pan_deg, limits.max_pan_deg)
        # 수직 우산 법선과 태양 광선 사이의 각도. 낮은 태양에서는 안정성 때문에 제한한다.
        target_tilt = clamp(90.0 - sun.elevation_deg, 0.0, limits.max_tilt_deg)
        reason = "sun normal tracking with mechanical limits"

    pan_step = _bounded_step(target_pan - current_pan_deg, limits)
    tilt_step = _bounded_step(target_tilt - current_tilt_deg, limits)
    return UmbrellaCommand(mode, sun, target_pan, target_tilt, pan_step, tilt_step, reason)


def save_visualization(
    command: UmbrellaCommand,
    robot_heading_deg: float,
    output: str,
) -> None:
    """태양 방향과 우산 목표를 top/side view PNG로 저장한다."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure = plt.figure(figsize=(10, 5), constrained_layout=True)
    top = figure.add_subplot(1, 2, 1, projection="polar")
    side = figure.add_subplot(1, 2, 2)

    top.set_theta_zero_location("N")
    top.set_theta_direction(-1)
    top.set_rlim(0, 1.1)
    top.set_yticklabels([])
    top.set_title("Top view (true north)")
    top.annotate(
        "Robot heading",
        xy=(math.radians(robot_heading_deg), 1.0),
        xytext=(math.radians(robot_heading_deg), 0.48),
        arrowprops={"arrowstyle": "->", "color": "tab:blue", "lw": 3},
        color="tab:blue",
        ha="center",
    )
    top.annotate(
        "Sun azimuth",
        xy=(math.radians(command.sun.azimuth_deg), 1.0),
        xytext=(math.radians(command.sun.azimuth_deg), 0.62),
        arrowprops={"arrowstyle": "->", "color": "goldenrod", "lw": 3},
        color="darkgoldenrod",
        ha="center",
    )

    elevation = math.radians(command.sun.elevation_deg)
    sun_x, sun_z = math.cos(elevation), math.sin(elevation)
    target_elevation = math.radians(90.0 - command.target_tilt_deg)
    umbrella_x, umbrella_z = math.cos(target_elevation), math.sin(target_elevation)
    side.axhline(0.0, color="0.35", lw=1)
    side.axvline(0.0, color="0.75", lw=1)
    side.arrow(0, 0, sun_x, sun_z, width=0.015, color="goldenrod", length_includes_head=True)
    side.arrow(0, 0, umbrella_x, umbrella_z, width=0.015, color="tab:green", length_includes_head=True)
    side.text(sun_x, sun_z, f" Sun {command.sun.elevation_deg:.1f} deg", color="darkgoldenrod")
    side.text(
        umbrella_x,
        umbrella_z,
        f" Umbrella tilt {command.target_tilt_deg:.1f} deg",
        color="tab:green",
    )
    side.set_xlim(-1.1, 1.3)
    side.set_ylim(-1.1, 1.2)
    side.set_aspect("equal", adjustable="box")
    side.set_xlabel("Horizontal direction toward Sun")
    side.set_ylabel("Up")
    side.set_title(f"Side view — {command.mode}")
    side.grid(True, alpha=0.3)

    figure.suptitle(
        f"Sun az={command.sun.azimuth_deg:.1f} deg, el={command.sun.elevation_deg:.1f} deg | "
        f"target pan={command.target_pan_deg:+.1f} deg, tilt={command.target_tilt_deg:.1f} deg"
    )
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=160)
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description="현재 태양 위치와 우산 pan/tilt 목표 계산")
    parser.add_argument("--latitude", type=float, required=True)
    parser.add_argument("--longitude", type=float, required=True)
    parser.add_argument("--timezone", default="Asia/Seoul")
    parser.add_argument("--heading", type=float, required=True, help="로봇의 진북 기준 heading")
    parser.add_argument("--pan", type=float, default=0.0)
    parser.add_argument("--tilt", type=float, default=0.0)
    parser.add_argument("--wind", type=float)
    parser.add_argument("--save-plot", help="top/side view PNG 저장 경로")
    args = parser.parse_args()

    now = datetime.now(ZoneInfo(args.timezone))
    sun = solar_position(now, args.latitude, args.longitude)
    command = plan_umbrella(sun, args.heading, args.pan, args.tilt, wind_m_s=args.wind)
    print(f"time={now.isoformat(timespec='seconds')}")
    print(f"sun azimuth={sun.azimuth_deg:.2f} elevation={sun.elevation_deg:.2f}")
    print(f"mode={command.mode} reason={command.reason}")
    print(f"target pan={command.target_pan_deg:+.2f} tilt={command.target_tilt_deg:+.2f}")
    print(f"next step pan={command.pan_step_deg:+.2f} tilt={command.tilt_step_deg:+.2f}")
    if args.save_plot:
        save_visualization(command, args.heading, args.save_plot)
        print(f"plot={Path(args.save_plot).resolve()}")


if __name__ == "__main__":
    main()
