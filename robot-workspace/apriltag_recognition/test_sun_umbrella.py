import unittest
from datetime import datetime, timezone

from sun_umbrella import SunPosition, UmbrellaLimits, plan_umbrella, save_visualization, solar_position


class SolarPositionTest(unittest.TestCase):
    def test_equinox_near_equator_noon_is_high(self):
        sun = solar_position(datetime(2026, 3, 20, 12, tzinfo=timezone.utc), 0.0, 0.0)
        self.assertGreater(sun.elevation_deg, 85.0)

    def test_timezone_is_required(self):
        with self.assertRaises(ValueError):
            solar_position(datetime(2026, 8, 7, 12), 37.5, 127.0)


class UmbrellaPolicyTest(unittest.TestCase):
    def test_tracks_relative_to_robot_heading(self):
        command = plan_umbrella(SunPosition(150.0, 60.0), 120.0, 0.0, 0.0)
        self.assertEqual(command.mode, "TRACK")
        self.assertAlmostEqual(command.target_pan_deg, 30.0)
        self.assertAlmostEqual(command.target_tilt_deg, 30.0)
        self.assertAlmostEqual(command.pan_step_deg, 5.0)
        self.assertAlmostEqual(command.tilt_step_deg, 5.0)

    def test_low_sun_parks(self):
        command = plan_umbrella(SunPosition(90.0, 2.0), 0.0, 20.0, 20.0)
        self.assertEqual(command.mode, "PARK")
        self.assertEqual(command.target_pan_deg, 0.0)
        self.assertEqual(command.target_tilt_deg, 0.0)

    def test_tilt_and_pan_are_limited(self):
        limits = UmbrellaLimits(max_tilt_deg=35.0, min_pan_deg=-80.0, max_pan_deg=80.0)
        command = plan_umbrella(SunPosition(180.0, 10.0), 0.0, 0.0, 0.0, limits)
        self.assertEqual(command.target_pan_deg, -80.0)  # wrap_180(180) == -180
        self.assertEqual(command.target_tilt_deg, 35.0)

    def test_deadband_suppresses_chatter(self):
        command = plan_umbrella(SunPosition(11.0, 79.0), 0.0, 10.0, 10.0)
        self.assertEqual(command.pan_step_deg, 0.0)
        self.assertEqual(command.tilt_step_deg, 0.0)

    def test_high_wind_parks(self):
        command = plan_umbrella(SunPosition(90.0, 45.0), 0.0, 10.0, 10.0, wind_m_s=9.0)
        self.assertEqual(command.mode, "PARK")

    def test_visualization_is_saved(self):
        import tempfile
        from pathlib import Path

        command = plan_umbrella(SunPosition(150.0, 60.0), 120.0, 0.0, 0.0)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "sun.png"
            save_visualization(command, 120.0, str(output))
            self.assertGreater(output.stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
