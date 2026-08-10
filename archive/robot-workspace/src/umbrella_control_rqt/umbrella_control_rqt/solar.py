"""Dependency-free solar elevation and unassigned motion selection."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any


def solar_elevation(when: datetime, latitude_deg: float, longitude_deg: float) -> float:
    if when.tzinfo is None or when.utcoffset() is None:
        raise ValueError("timezone-aware datetime required")
    day = when.timetuple().tm_yday
    hour = when.hour + when.minute / 60.0 + when.second / 3600.0
    leap = when.year % 4 == 0 and (when.year % 100 != 0 or when.year % 400 == 0)
    gamma = 2.0 * math.pi / (366 if leap else 365) * (day - 1 + (hour - 12.0) / 24.0)
    equation = 229.18 * (
        0.000075 + 0.001868 * math.cos(gamma) - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2 * gamma) - 0.040849 * math.sin(2 * gamma)
    )
    declination = (
        0.006918 - 0.399912 * math.cos(gamma) + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2 * gamma) + 0.000907 * math.sin(2 * gamma)
        - 0.002697 * math.cos(3 * gamma) + 0.00148 * math.sin(3 * gamma)
    )
    offset = when.utcoffset().total_seconds() / 3600.0
    solar_minutes = (hour * 60 + equation + 4 * longitude_deg - 60 * offset) % 1440
    hour_angle = math.radians(solar_minutes / 4 - 180)
    latitude = math.radians(latitude_deg)
    cos_zenith = (
        math.sin(latitude) * math.sin(declination)
        + math.cos(latitude) * math.cos(declination) * math.cos(hour_angle)
    )
    return 90.0 - math.degrees(math.acos(max(-1.0, min(1.0, cos_zenith))))


def select_motion(elevation_deg: float, motions: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next(
        (
            item for item in motions
            if float(item["min_elevation_deg"]) <= elevation_deg < float(item["max_elevation_deg"])
        ),
        None,
    )
