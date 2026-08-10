from datetime import datetime
from zoneinfo import ZoneInfo

from umbrella_control_rqt.solar import select_motion, solar_elevation


def test_daejeon_summer_noon_is_high():
    when = datetime(2026, 8, 7, 12, 30, tzinfo=ZoneInfo("Asia/Seoul"))
    assert solar_elevation(when, 36.3504, 127.3845) > 60.0


def test_motion_selection_keeps_id_unassigned():
    motions = [{"name": "LOW", "min_elevation_deg": 0, "max_elevation_deg": 25, "motion_id": None}]
    assert select_motion(10, motions)["motion_id"] is None
