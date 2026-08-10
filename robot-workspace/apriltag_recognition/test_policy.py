import unittest

import cv2
import numpy as np

from umbrella_follower import (FollowPolicy, Observation, detect_tag,
                               dictionary_from_name, make_detector_parameters,
                               validate_vpi_detector)


class PolicyTest(unittest.TestCase):
    def setUp(self):
        self.policy = FollowPolicy({"target_distance_m": 1.2, "distance_tolerance_m": 0.2,
                                    "turn_enter_deg": 10, "turn_exit_deg": 6})

    @staticmethod
    def obs(z, angle):
        import math
        x = math.tan(math.radians(angle)) * z
        return Observation(x, z, math.hypot(x, z), angle, 0)

    def test_distance_states(self):
        self.assertEqual(self.policy.decide(self.obs(1.6, 0)), "FORWARD")
        self.assertEqual(self.policy.decide(self.obs(0.8, 0)), "BACKWARD")
        self.assertEqual(self.policy.decide(self.obs(1.2, 0)), "HOLD")

    def test_turn_and_hysteresis(self):
        self.assertEqual(self.policy.decide(self.obs(1.2, 12)), "TURN_RIGHT")
        self.assertEqual(self.policy.decide(self.obs(1.2, 8)), "TURN_RIGHT")
        self.assertEqual(self.policy.decide(self.obs(1.2, 5)), "HOLD")
        self.assertEqual(self.policy.decide(self.obs(1.2, -12)), "TURN_LEFT")

    def test_lost(self):
        self.assertEqual(self.policy.decide(None), "LOST")


class TiltedTagDetectionTest(unittest.TestCase):
    def test_perspective_tilt_is_detected(self):
        dictionary = dictionary_from_name("DICT_APRILTAG_36h11")
        marker = np.full((260, 260), 255, dtype=np.uint8)
        marker[30:230, 30:230] = cv2.aruco.drawMarker(dictionary, 0, 200)
        source = np.float32([[0, 0], [259, 0], [259, 259], [0, 259]])
        # 위쪽 변이 짧고 기울어진 강한 원근 변형을 만든다.
        target = np.float32([[555, 260], [720, 310], [750, 450], [515, 490]])
        transform = cv2.getPerspectiveTransform(source, target)
        gray = cv2.warpPerspective(marker, transform, (1280, 720), borderValue=190)
        frame = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        camera_matrix = np.array([[900.0, 0, 640], [0, 900.0, 360], [0, 0, 1]])
        detector_cfg = {"retry_scales": [1.0, 1.5, 2.0]}

        position, _ = detect_tag(
            frame, dictionary, 0, 0.18, camera_matrix, np.zeros(5),
            make_detector_parameters(detector_cfg), detector_cfg,
        )
        self.assertIsNotNone(position)

    def test_vpi_backend_validation_rejects_empty_detector(self):
        class EmptyDetector:
            backend = "BROKEN"

            @staticmethod
            def detect(_image):
                return []

        with self.assertRaises(RuntimeError):
            validate_vpi_detector(EmptyDetector(), dictionary_from_name("DICT_APRILTAG_36h11"), 0, 1280, 720)


if __name__ == "__main__":
    unittest.main()
