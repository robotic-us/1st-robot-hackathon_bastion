#!/usr/bin/env python3
"""AprilTag 기반 양산 운반 로봇 추종기.

기본 실행은 vision-only이다. 실제 모션 전송은 --enable-motion을 명시해야 한다.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np


@dataclass
class Observation:
    x_m: float
    z_m: float
    distance_m: float
    bearing_deg: float
    seen_at: float


class EmaFilter:
    def __init__(self, alpha: float) -> None:
        self.alpha = alpha
        self.value: Optional[np.ndarray] = None

    def update(self, x_m: float, z_m: float, now: float) -> Observation:
        current = np.array([x_m, z_m], dtype=np.float64)
        self.value = current if self.value is None else self.alpha * current + (1 - self.alpha) * self.value
        x, z = self.value
        return Observation(float(x), float(z), float(math.hypot(x, z)), float(math.degrees(math.atan2(x, z))), now)


class FollowPolicy:
    """카메라 기준 +x=오른쪽인 태그를 따라가는 히스테리시스 정책."""

    def __init__(self, cfg: dict[str, Any]) -> None:
        self.target = float(cfg["target_distance_m"])
        self.distance_tolerance = float(cfg["distance_tolerance_m"])
        self.turn_enter = float(cfg["turn_enter_deg"])
        self.turn_exit = float(cfg["turn_exit_deg"])
        self.last_state = "LOST"

    def decide(self, obs: Optional[Observation]) -> str:
        if obs is None:
            self.last_state = "LOST"
        else:
            abs_angle = abs(obs.bearing_deg)
            turning = self.last_state in ("TURN_LEFT", "TURN_RIGHT")
            turn_threshold = self.turn_exit if turning else self.turn_enter
            if abs_angle > turn_threshold:
                # 태그가 영상 오른쪽이면 로봇도 오른쪽으로 회전한다.
                self.last_state = "TURN_RIGHT" if obs.bearing_deg > 0 else "TURN_LEFT"
            elif obs.z_m > self.target + self.distance_tolerance:
                self.last_state = "FORWARD"
            elif obs.z_m < self.target - self.distance_tolerance:
                self.last_state = "BACKWARD"
            else:
                self.last_state = "HOLD"
        return self.last_state


class MotionController:
    """phorce의 단일 모션 슬롯 계약을 지키는 논블로킹 전송기."""

    def __init__(self, robot: Any, mapping: dict[str, Optional[int]], repeat_interval_s: float) -> None:
        self.robot = robot
        self.mapping = mapping
        self.repeat_interval_s = repeat_interval_s
        self.handle: Any = None
        self.last_state: Optional[str] = None
        self.last_started = 0.0

    def tick(self, state: str, now: float) -> None:
        if self.handle is not None:
            if not self.handle.done:
                return
            try:
                result = self.handle.wait()
                if not result.ok:
                    print(f"[phorce] motion failed: {result.detail}")
            finally:
                self.handle = None

        motion_id = self.mapping.get(state)
        if motion_id is None:
            return
        if state == self.last_state and now - self.last_started < self.repeat_interval_s:
            return
        self.handle = self.robot.play_async(int(motion_id))
        self.last_state = state
        self.last_started = now
        print(f"[phorce] {state} -> motion {motion_id}")


def load_json(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_calibration(path: str) -> tuple[np.ndarray, np.ndarray]:
    cfg = load_json(path)
    return np.asarray(cfg["camera_matrix"], dtype=np.float64), np.asarray(cfg["dist_coeffs"], dtype=np.float64)


def dictionary_from_name(name: str) -> Any:
    if not hasattr(cv2.aruco, name):
        raise ValueError(f"지원하지 않는 AprilTag dictionary: {name}")
    return cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, name))


def make_detector_parameters(cfg: Optional[dict[str, Any]] = None) -> Any:
    """비스듬하거나 작게 보이는 태그에 맞춘 보수적인 탐지 파라미터."""
    cfg = cfg or {}
    params = cv2.aruco.DetectorParameters_create()
    params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    params.cornerRefinementWinSize = int(cfg.get("corner_refinement_win_size", 7))
    params.cornerRefinementMaxIterations = 50
    params.cornerRefinementMinAccuracy = 0.01
    params.adaptiveThreshWinSizeMin = 3
    params.adaptiveThreshWinSizeMax = int(cfg.get("adaptive_thresh_win_size_max", 53))
    params.adaptiveThreshWinSizeStep = 4
    params.minMarkerPerimeterRate = float(cfg.get("min_marker_perimeter_rate", 0.015))
    params.polygonalApproxAccuracyRate = float(cfg.get("polygonal_approx_accuracy_rate", 0.05))
    params.perspectiveRemovePixelPerCell = int(cfg.get("perspective_pixels_per_cell", 8))
    params.perspectiveRemoveIgnoredMarginPerCell = 0.08
    # ID의 오류 정정 한계는 느슨하게 하지 않아 오검출 가능성을 억제한다.
    params.errorCorrectionRate = 0.6
    return params


def _detect_at_scale(gray: np.ndarray, dictionary: Any, parameters: Any,
                     scale: float) -> tuple[list[np.ndarray], Optional[np.ndarray], Any]:
    image = gray if scale == 1.0 else cv2.resize(
        gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC
    )
    corners, ids, rejected = cv2.aruco.detectMarkers(image, dictionary, parameters=parameters)
    if scale != 1.0:
        corners = [corner / scale for corner in corners]
    return corners, ids, rejected


def pose_from_corners(frame: np.ndarray, corners: np.ndarray, target_id: int, tag_size_m: float,
                      camera_matrix: np.ndarray, dist_coeffs: np.ndarray
                      ) -> tuple[tuple[float, float], list[np.ndarray]]:
    marker_corners = np.asarray(corners, dtype=np.float32).reshape(1, 4, 2)
    rvecs, tvecs, _ = cv2.aruco.estimatePoseSingleMarkers(
        [marker_corners], tag_size_m, camera_matrix, dist_coeffs
    )
    tvec = tvecs[0][0]
    cv2.drawFrameAxes(frame, camera_matrix, dist_coeffs, rvecs[0][0], tvec, tag_size_m * 0.5)
    cv2.aruco.drawDetectedMarkers(frame, [marker_corners], np.array([[target_id]], dtype=np.int32))
    return (float(tvec[0]), float(tvec[2])), [marker_corners]


def detect_tag_vpi(frame: np.ndarray, detector: Any, target_id: int, tag_size_m: float,
                   camera_matrix: np.ndarray, dist_coeffs: np.ndarray
                   ) -> tuple[Optional[tuple[float, float]], Any]:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    matches = [item for item in detector.detect(gray) if int(item[0]) == target_id]
    if not matches:
        return None, []
    # VPI decision margin을 우선하고, 동점이면 더 큰 태그를 선택한다.
    selected = max(matches, key=lambda item: (
        float(item[2]), abs(cv2.contourArea(np.asarray(item[1], dtype=np.float32)))
    ))
    return pose_from_corners(frame, selected[1], target_id, tag_size_m, camera_matrix, dist_coeffs)


def validate_vpi_detector(detector: Any, dictionary: Any, target_id: int,
                          width: int, height: int) -> None:
    """백엔드가 정상 정사각형 태그를 실제로 디코딩하는지 시작 시 검증한다."""
    marker_size = max(96, min(300, width // 3, height // 2))
    probe = np.full((height, width), 255, dtype=np.uint8)
    marker = cv2.aruco.drawMarker(dictionary, target_id, marker_size)
    x = (width - marker_size) // 2
    y = (height - marker_size) // 2
    probe[y:y + marker_size, x:x + marker_size] = marker
    if not any(int(item[0]) == target_id for item in detector.detect(probe)):
        raise RuntimeError(f"{detector.backend} backend가 자체검사 태그 ID {target_id}를 검출하지 못함")


def detect_tag(frame: np.ndarray, dictionary: Any, target_id: int, tag_size_m: float,
               camera_matrix: np.ndarray, dist_coeffs: np.ndarray,
               parameters: Optional[Any] = None, detector_cfg: Optional[dict[str, Any]] = None
               ) -> tuple[Optional[tuple[float, float]], Any]:
    detector_cfg = detector_cfg or {}
    parameters = parameters or make_detector_parameters(detector_cfg)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    scales = [float(value) for value in detector_cfg.get("retry_scales", [1.0, 1.5, 2.0])]
    candidates: list[np.ndarray] = []
    rejected: Any = []

    # 원본을 먼저 사용해 CPU 사용량을 낮추고, 실패할 때만 대비/크기를 보강한다.
    for pass_index, scale in enumerate(scales):
        if pass_index == 0:
            image = gray
        else:
            # 정상 검출 때는 CLAHE와 확대 영상을 만들지 않는다. LOST 복구 경로에서만
            # 한 번 생성하여 모든 재시도 스케일이 공유한다.
            if pass_index == 1:
                clahe = cv2.createCLAHE(
                    clipLimit=float(detector_cfg.get("clahe_clip_limit", 2.0)),
                    tileGridSize=(8, 8),
                )
                enhanced = clahe.apply(gray)
            image = enhanced
        corners, ids, rejected = _detect_at_scale(image, dictionary, parameters, scale)
        if ids is None:
            continue
        for index, marker_id in enumerate(ids.flatten()):
            if int(marker_id) == target_id:
                candidates.append(corners[index])
        if candidates:
            break

    if not candidates:
        return None, rejected
    # 동일 ID 후보가 여럿이면 영상에서 가장 큰 것(가장 신뢰할 수 있는 것)을 쓴다.
    target_corners = max(candidates, key=lambda c: abs(cv2.contourArea(c.reshape(-1, 2))))
    return pose_from_corners(frame, target_corners, target_id, tag_size_m, camera_matrix, dist_coeffs)


def open_camera(cfg: dict[str, Any]) -> cv2.VideoCapture:
    device = cfg["device"]
    cap = cv2.VideoCapture(device, cv2.CAP_V4L2) if isinstance(device, int) else cv2.VideoCapture(device)
    # C270 같은 UVC 웹캠은 720p 기본 YUYV 모드에서 5~10fps로 제한될 수 있다.
    # 해상도를 설정하기 전에 MJPEG를 요청하면 USB 대역폭을 줄여 높은 fps를 사용할 수 있다.
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(cfg["width"]))
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(cfg["height"]))
    cap.set(cv2.CAP_PROP_FPS, int(cfg["fps"]))
    if not cap.isOpened():
        raise RuntimeError(f"카메라를 열 수 없습니다: {device} (/dev/video* 연결/권한/점유 확인)")
    return cap


def run(args: argparse.Namespace) -> None:
    cfg = load_json(args.config)
    camera_matrix, dist_coeffs = load_calibration(cfg["camera"]["calibration_file"])
    dictionary = dictionary_from_name(cfg["tag"]["family"])
    detector_cfg = cfg.get("detector", {})
    detector_parameters = make_detector_parameters(detector_cfg)
    cap = open_camera(cfg["camera"])
    filt = EmaFilter(float(cfg["tracking"]["ema_alpha"]))
    policy = FollowPolicy(cfg["tracking"])
    last_obs: Optional[Observation] = None
    last_printed: Optional[str] = None
    missed_frames = 0
    vpi_detector: Any = None
    vpi_initialized = False

    robot_context = None
    controller = None
    if args.enable_motion:
        import phorce
        robot_context = phorce.connect()
        robot = robot_context.__enter__()
        report = robot.doctor()
        if not report.ok:
            robot_context.__exit__(None, None, None)
            raise RuntimeError(f"phorce doctor 실패: {report.issues}")
        controller = MotionController(robot, cfg["motion"], float(cfg["motion"]["repeat_interval_s"]))

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError("웹캠 프레임을 읽지 못했습니다")
            now = time.monotonic()
            if not vpi_initialized and detector_cfg.get("backend", "vpi") == "vpi":
                vpi_initialized = True
                try:
                    import vpi_apriltag
                    try:
                        vpi_detector = vpi_apriltag.Detector(frame.shape[1], frame.shape[0], True)
                        validate_vpi_detector(
                            vpi_detector, dictionary, int(cfg["tag"]["id"]), frame.shape[1], frame.shape[0]
                        )
                    except Exception as pva_error:
                        print(f"[vision] VPI/PVA 자체검사 실패, VPI/CPU 재시도: {pva_error}")
                        vpi_detector = vpi_apriltag.Detector(frame.shape[1], frame.shape[0], False)
                        validate_vpi_detector(
                            vpi_detector, dictionary, int(cfg["tag"]["id"]), frame.shape[1], frame.shape[0]
                        )
                    print(f"[vision] NVIDIA VPI AprilTag 활성화 — backend={vpi_detector.backend}")
                except Exception as error:
                    print(f"[vision] VPI 초기화 실패 — OpenCV fallback 사용: {error}")

            if vpi_detector is not None:
                try:
                    position, _ = detect_tag_vpi(
                        frame, vpi_detector, int(cfg["tag"]["id"]), float(cfg["tag"]["size_m"]),
                        camera_matrix, dist_coeffs,
                    )
                except Exception as error:
                    print(f"[vision] VPI 실행 실패 — OpenCV fallback으로 전환: {error}")
                    vpi_detector = None
                    position = None
            else:
                heavy_retry_interval = max(1, int(detector_cfg.get("recovery_retry_interval_frames", 5)))
                detection_cfg = detector_cfg
                if missed_frames > 0 and missed_frames % heavy_retry_interval != 0:
                    detection_cfg = dict(detector_cfg)
                    detection_cfg["retry_scales"] = [1.0]
                position, _ = detect_tag(
                    frame, dictionary, int(cfg["tag"]["id"]), float(cfg["tag"]["size_m"]),
                    camera_matrix, dist_coeffs, detector_parameters, detection_cfg,
                )
            if position is not None:
                missed_frames = 0
                last_obs = filt.update(position[0], position[1], now)
            else:
                missed_frames += 1
            active_obs = last_obs
            if active_obs is not None and now - active_obs.seen_at > float(cfg["tracking"]["lost_timeout_s"]):
                active_obs = None
            state = policy.decide(active_obs)
            if state != last_printed:
                detail = "" if active_obs is None else f" distance={active_obs.distance_m:.2f}m bearing={active_obs.bearing_deg:+.1f}deg"
                print(f"[vision] {state}{detail}")
                last_printed = state
            if controller is not None:
                controller.tick(state, now)

            if active_obs is not None:
                cv2.putText(frame, f"{state}  {active_obs.distance_m:.2f}m  {active_obs.bearing_deg:+.1f}deg",
                            (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            else:
                cv2.putText(frame, "LOST", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
            if not args.headless:
                cv2.imshow("umbrella follower (q: quit)", frame)
                if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                    break
    finally:
        cap.release()
        cv2.destroyAllWindows()
        if robot_context is not None:
            robot_context.__exit__(None, None, None)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--enable-motion", action="store_true", help="실물 로봇에 모션을 전송")
    parser.add_argument("--headless", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    run(parse_args())
