#!/usr/bin/env python3
"""체커보드로 웹캠 내부 파라미터를 구해 JSON으로 저장한다."""

import argparse
import json

import cv2
import numpy as np


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--device", type=int, default=0)
    p.add_argument("--cols", type=int, default=9, help="체커보드 내부 코너 열 수")
    p.add_argument("--rows", type=int, default=6, help="체커보드 내부 코너 행 수")
    p.add_argument("--square-m", type=float, default=0.024)
    p.add_argument("--samples", type=int, default=20)
    p.add_argument("--output", default="camera_calibration.json")
    args = p.parse_args()

    cap = cv2.VideoCapture(args.device)
    if not cap.isOpened():
        raise RuntimeError(f"카메라를 열 수 없습니다: {args.device}")
    object_template = np.zeros((args.rows * args.cols, 3), np.float32)
    object_template[:, :2] = np.mgrid[0:args.cols, 0:args.rows].T.reshape(-1, 2) * args.square_m
    object_points, image_points = [], []
    image_size = None
    print("체커보드를 여러 각도에서 비추고 SPACE로 샘플을 저장하세요. q는 종료입니다.")
    try:
        while len(object_points) < args.samples:
            ok, frame = cap.read()
            if not ok:
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            image_size = gray.shape[::-1]
            found, corners = cv2.findChessboardCorners(gray, (args.cols, args.rows))
            if found:
                corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1),
                                           (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001))
                cv2.drawChessboardCorners(frame, (args.cols, args.rows), corners, found)
            cv2.putText(frame, f"samples: {len(object_points)}/{args.samples}", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.imshow("camera calibration", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q") or key == 27:
                return
            if key == ord(" ") and found:
                object_points.append(object_template.copy())
                image_points.append(corners)
                print(f"sample {len(object_points)}/{args.samples}")
    finally:
        cap.release()
        cv2.destroyAllWindows()

    rms, matrix, distortion, _, _ = cv2.calibrateCamera(object_points, image_points, image_size, None, None)
    result = {"rms_error": rms, "image_size": image_size, "camera_matrix": matrix.tolist(),
              "dist_coeffs": distortion.reshape(-1).tolist()}
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(f"saved {args.output} (RMS error: {rms:.4f})")


if __name__ == "__main__":
    main()
