#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import mimetypes
import os
import subprocess
import threading
import time
import traceback
from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
MOTION_DIR = Path(os.environ.get("PHORCE_MOTION_DIR", "/media/phorce/9016-4EF8/Motions"))
LOCAL_MOTION_DIR = ROOT.parent
STATE_FILE = ROOT / "dashboard_state.json"
KST = ZoneInfo("Asia/Seoul")
ANGLE_TOLERANCE_DEG = 3.0
AXIS_COUNT = 12
UMBRELLA_HEIGHT_AXIS = 1  # node 0x03 / MD1; never allow a negative relative angle
CONTROL_SETTLE_SECONDS = 3
PARKING_TO_MOTION = {spot: spot + 3 for spot in range(1, 8)}
HEIGHT_SLOT_BY_MIN_CM = [(190, 45), (180, 44), (170, 43), (160, 42), (150, 41)]
TILT_CHOICES = [(-40, 28), (-30, 27), (-20, 26), (-10, 25), (0, None),
                (10, 21), (20, 22), (30, 23), (40, 24)]
MANUAL_SLOTS = (set(range(1, 11)) | set(range(14, 29)) | set(range(31, 39))
                | set(range(41, 51)))


@dataclass
class SunPosition:
    azimuth_deg: float
    elevation_deg: float
    tilt_deg: float
    selected_tilt_deg: int
    motion_id: int | None


def solar_position(when: datetime, latitude_deg: float, longitude_deg: float) -> tuple[float, float]:
    """NOAA fractional-year approximation; azimuth is clockwise from north."""
    if when.tzinfo is None or when.utcoffset() is None:
        when = when.replace(tzinfo=KST)
    day = when.timetuple().tm_yday
    hour = when.hour + when.minute / 60 + when.second / 3600
    leap = when.year % 4 == 0 and (when.year % 100 != 0 or when.year % 400 == 0)
    gamma = 2 * math.pi / (366 if leap else 365) * (day - 1 + (hour - 12) / 24)
    eqtime = 229.18 * (0.000075 + 0.001868 * math.cos(gamma)
                       - 0.032077 * math.sin(gamma) - 0.014615 * math.cos(2 * gamma)
                       - 0.040849 * math.sin(2 * gamma))
    decl = (0.006918 - 0.399912 * math.cos(gamma) + 0.070257 * math.sin(gamma)
            - 0.006758 * math.cos(2 * gamma) + 0.000907 * math.sin(2 * gamma)
            - 0.002697 * math.cos(3 * gamma) + 0.00148 * math.sin(3 * gamma))
    tz_hours = when.utcoffset().total_seconds() / 3600
    solar_minutes = (hour * 60 + eqtime + 4 * longitude_deg - 60 * tz_hours) % 1440
    hour_angle = math.radians(solar_minutes / 4 - 180)
    latitude = math.radians(latitude_deg)
    cos_zenith = (math.sin(latitude) * math.sin(decl)
                   + math.cos(latitude) * math.cos(decl) * math.cos(hour_angle))
    elevation = 90 - math.degrees(math.acos(max(-1, min(1, cos_zenith))))
    azimuth = (math.degrees(math.atan2(
        math.sin(hour_angle),
        math.cos(hour_angle) * math.sin(latitude) - math.tan(decl) * math.cos(latitude),
    )) + 180) % 360
    return azimuth, elevation


def calculate_sun(when: datetime, latitude: float, longitude: float,
                  heading_deg: float = 192.7) -> SunPosition:
    azimuth, elevation = solar_position(when, latitude, longitude)
    # Rear view convention: the vehicle heading is 192.7 deg, 0 tilt is
    # 12 o'clock, and clockwise toward west is positive. Project the sun
    # vector onto the robot's lateral/vertical tilt plane. East is negative,
    # west is positive; azimuth remains an internal value and is not shown.
    delta = math.radians(((azimuth - heading_deg + 180) % 360) - 180)
    elevation_rad = math.radians(elevation)
    tilt = math.degrees(math.atan2(math.cos(elevation_rad) * math.sin(delta),
                                   math.sin(elevation_rad)))
    if elevation <= 0:
        tilt = 0.0
    selected, motion_id = min(TILT_CHOICES, key=lambda item: abs(item[0] - tilt))
    return SunPosition(azimuth, elevation, tilt, selected, motion_id)


class MotionLibrary:
    def __init__(self, root: Path):
        self.root = root

    def motion(self, slot: int) -> dict[str, Any]:
        csv_path = self.root / f"motion_{slot:02}.csv"
        memo_path = self.root / f"motion_{slot:02}.memo.json"
        if not csv_path.exists() or not memo_path.exists():
            csv_path = LOCAL_MOTION_DIR / f"motion_{slot:02}.csv"
            memo_path = LOCAL_MOTION_DIR / f"motion_{slot:02}.memo.json"
        if not csv_path.exists() or not memo_path.exists():
            raise FileNotFoundError(f"모션 {slot} 파일이 없습니다")
        raw = csv_path.read_bytes()
        memo = json.loads(memo_path.read_text())
        digest = hashlib.sha256(raw).hexdigest()
        if memo.get("motion_sha256") != digest:
            raise RuntimeError(f"모션 {slot} 체크섬이 일치하지 않습니다")
        rows = list(csv.reader(raw.decode().splitlines()))
        axes: dict[int, list[float]] = {}
        for row in rows[4:]:
            values = [float(cell.split(",")[0]) for cell in row[3:] if cell != "-"]
            if values:
                axes[int(row[2][2:])] = values
        starts = {axis: values[0] for axis, values in axes.items()}
        ends = {axis: values[-1] for axis, values in axes.items()}
        return {"slot": slot, "name": rows[4][1], "starts": starts, "ends": ends,
                "minimums": {axis: min(values) for axis, values in axes.items()},
                "memo": memo.get("memo", "")}


class DashboardState:
    def __init__(self):
        self.lock = threading.Lock()
        self.data = {"height_slot": None, "height_cm": None, "tilt_slot": None,
                     "tilt_deg": 0, "last_parking": None, "history": []}
        if STATE_FILE.exists():
            try:
                self.data.update(json.loads(STATE_FILE.read_text()))
            except (OSError, ValueError):
                pass
        # The dashboard's coordinate system is relative. Every server launch starts
        # with all axes at the user-declared origin and never consults robot feedback.
        self.data["motor_positions_deg"] = [0.0] * AXIS_COUNT
        self.data["last_motion_slot"] = None
        self.data["height_slot"] = None
        self.data["height_cm"] = None
        self.data["tilt_slot"] = None
        self.data["tilt_deg"] = 0

    def update(self, **changes: Any) -> None:
        with self.lock:
            self.data.update(changes)
            STATE_FILE.write_text(json.dumps(self.data, ensure_ascii=False, indent=2) + "\n")

    def event(self, message: str, kind: str = "info") -> None:
        with self.lock:
            history = self.data.setdefault("history", [])
            history.insert(0, {"at": datetime.now(KST).isoformat(timespec="seconds"),
                               "message": message, "kind": kind})
            del history[30:]
            STATE_FILE.write_text(json.dumps(self.data, ensure_ascii=False, indent=2) + "\n")

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return json.loads(json.dumps(self.data))


class JobManager:
    def __init__(self, library: MotionLibrary, state: DashboardState,
                 domain_id: int, dry_run: bool):
        self.library, self.state = library, state
        self.domain_id, self.dry_run = domain_id, dry_run
        self.lock = threading.Lock()
        self.job: dict[str, Any] | None = None

    def height_slot(self, height_cm: float) -> int | None:
        for minimum, slot in HEIGHT_SLOT_BY_MIN_CM:
            if height_cm >= minimum:
                return slot
        return None

    def transition_plan(self, current_slot: int | None, target_slot: int | None,
                        return_offset: int) -> list[dict[str, Any]]:
        plan = []
        if current_slot == target_slot:
            return plan
        if current_slot is not None:
            plan.append({"type": "motion", "slot": current_slot + return_offset})
        if target_slot is not None:
            plan.append({"type": "motion", "slot": target_slot})
        return plan

    def build_plan(self, request: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        kind = request.get("kind")
        current = self.state.snapshot()
        effects: dict[str, Any] = {}
        if kind == "parking":
            spot = int(request["spot"])
            if spot not in PARKING_TO_MOTION:
                raise ValueError("주차 위치는 1~7만 가능합니다")
            outbound = PARKING_TO_MOTION[spot]
            plan = [{"type": "motion", "slot": outbound}, {"type": "wait", "seconds": 5},
                    {"type": "motion", "slot": outbound + 10}]
            umbrella_returns = (self.transition_plan(current.get("tilt_slot"), None, 10)
                                + self.transition_plan(current.get("height_slot"), None, 5))
            if umbrella_returns:
                plan.append({"type": "wait", "seconds": CONTROL_SETTLE_SECONDS})
                for index, step in enumerate(umbrella_returns):
                    if index:
                        plan.append({"type": "wait", "seconds": CONTROL_SETTLE_SECONDS})
                    plan.append(step)
            effects = {"last_parking": spot, "tilt_slot": None, "tilt_deg": 0,
                       "height_slot": None, "height_cm": None}
            return plan, effects
        if kind == "height":
            height = float(request["height_cm"])
            target = self.height_slot(height)
            plan = self.transition_plan(current.get("height_slot"), target, 5)
            effects = {"height_slot": target, "height_cm": height}
            return plan, effects
        if kind == "tilt":
            target = request.get("motion_id")
            target = int(target) if target is not None else None
            if target not in [None, 21, 22, 23, 24, 25, 26, 27, 28]:
                raise ValueError("지원하지 않는 기울기 모션입니다")
            plan = self.transition_plan(current.get("tilt_slot"), target, 10)
            selected = 0 if target is None else next(angle for angle, slot in TILT_CHOICES if slot == target)
            effects = {"tilt_slot": target, "tilt_deg": selected}
            return plan, effects
        if kind == "manual":
            slot = int(request["slot"])
            if slot not in MANUAL_SLOTS:
                raise ValueError(f"수동 실행이 허용되지 않은 슬롯입니다: {slot}")
            effects = {}
            if 21 <= slot <= 28:
                selected = next(angle for angle, motion_slot in TILT_CHOICES
                                if motion_slot == slot)
                effects = {"tilt_slot": slot, "tilt_deg": selected}
            elif 31 <= slot <= 38:
                effects = {"tilt_slot": None, "tilt_deg": 0}
            elif 41 <= slot <= 45:
                effects = {"height_slot": slot, "height_cm": None}
            elif 46 <= slot <= 50:
                effects = {"height_slot": None, "height_cm": None}
            return [{"type": "motion", "slot": slot}], effects
        raise ValueError("알 수 없는 명령입니다")

    def safety_check(self, plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
        warnings: list[dict[str, Any]] = []
        expected = list(self.state.snapshot()["motor_positions_deg"])
        for step in plan:
            if step["type"] != "motion":
                continue
            motion = self.library.motion(step["slot"])
            mismatches = []
            for axis, start in motion["starts"].items():
                actual = expected[axis]
                if abs(actual - start) > ANGLE_TOLERANCE_DEG:
                    mismatches.append({"axis": f"MD{axis}", "expected": round(start, 1),
                                       "actual": round(actual, 1),
                                       "difference": round(actual - start, 1)})
            if mismatches:
                warnings.append({"slot": step["slot"], "reason": "이전 종료각과 시작각 불일치",
                                 "mismatches": mismatches})
            if motion["minimums"].get(UMBRELLA_HEIGHT_AXIS, 0.0) < 0:
                warnings.append({"slot": step["slot"],
                                 "reason": "양산 높이 모터가 상대 원점(0°) 아래로 내려갑니다",
                                 "hard_block": True})
            for axis, end in motion["ends"].items():
                expected[axis] = end
        return warnings

    def submit(self, request: dict[str, Any]) -> dict[str, Any]:
        plan, effects = self.build_plan(request)
        warnings = self.safety_check(plan) if plan else []
        if warnings:
            return {"accepted": False, "warning": True, "warnings": warnings,
                    "hard_block": True, "plan": plan,
                    "message": "이전 종료각과 시작각이 달라 실행을 차단했습니다."}
        with self.lock:
            if self.job and self.job["status"] == "running":
                raise RuntimeError("다른 동작이 실행 중입니다")
            self.job = {"status": "running", "label": request.get("label", request.get("kind")),
                        "step": 0, "total": len(plan), "current": "준비 중", "error": None,
                        "started_at": datetime.now(KST).isoformat(timespec="seconds")}
        threading.Thread(target=self._run, args=(plan, effects), daemon=True).start()
        return {"accepted": True, "warning": bool(warnings), "plan": plan,
                "job": self.snapshot()}

    def _run(self, plan: list[dict[str, Any]], effects: dict[str, Any]) -> None:
        try:
            if not plan:
                self.state.update(**effects)
                self.state.event("변경할 모션이 없습니다")
            for index, step in enumerate(plan, 1):
                with self.lock:
                    self.job.update(step=index, current=(
                        f"{step['seconds']}초 안정화 대기 중" if step["type"] == "wait"
                        else f"모션 {step['slot']} 실행 중"))
                if step["type"] == "wait":
                    time.sleep(0.25 if self.dry_run else float(step["seconds"]))
                else:
                    self._play(int(step["slot"]))
                    motion = self.library.motion(int(step["slot"]))
                    positions = list(self.state.snapshot()["motor_positions_deg"])
                    for axis, end in motion["ends"].items():
                        positions[axis] = end
                    self.state.update(motor_positions_deg=positions,
                                      last_motion_slot=int(step["slot"]))
            self.state.update(**effects)
            self.state.event(f"{self.job['label']} 완료", "success")
            with self.lock:
                self.job.update(status="completed", current="완료")
        except Exception as exc:
            self.state.event(f"동작 실패: {exc}", "error")
            with self.lock:
                self.job.update(status="failed", current="실패", error=str(exc))

    def _play(self, slot: int) -> None:
        if self.dry_run:
            time.sleep(0.18)
            return
        cmd = ["phorce", "play", str(slot), "--target", "robot", "--domain-id",
               str(self.domain_id), "--json"]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        raw = proc.stdout.strip() or proc.stderr.strip()
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = {}
        if proc.returncode != 0 or not payload.get("ok"):
            raise RuntimeError(payload.get("detail") or payload.get("error") or raw
                               or f"모션 {slot} 실패")

    def snapshot(self) -> dict[str, Any] | None:
        with self.lock:
            return json.loads(json.dumps(self.job)) if self.job else None


class AppHandler(BaseHTTPRequestHandler):
    server_version = "UmbrellaDashboard/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[{self.log_date_time_string()}] {fmt % args}")

    @property
    def app(self) -> "DashboardServer":
        return self.server  # type: ignore[return-value]

    def send_json(self, payload: Any, status: int = 200) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/state":
            self.send_json({"state": self.app.state.snapshot(), "job": self.app.jobs.snapshot(),
                            "dry_run": self.app.jobs.dry_run,
                            "now": datetime.now(KST).isoformat(timespec="seconds")})
            return
        if path == "/api/health":
            self.send_json({"ok": True})
            return
        target = STATIC / ("index.html" if path == "/" else path.lstrip("/"))
        try:
            target = target.resolve()
            if STATIC.resolve() not in target.parents and target != STATIC.resolve():
                raise FileNotFoundError
            raw = target.read_bytes()
        except (OSError, ValueError):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self) -> None:
        try:
            request = self.read_json()
            if self.path == "/api/solar":
                when = datetime.fromisoformat(request["datetime"])
                if when.tzinfo is None:
                    when = when.replace(tzinfo=KST)
                result = calculate_sun(when, float(request["latitude"]), float(request["longitude"]))
                self.send_json(result.__dict__)
                return
            if self.path == "/api/action":
                self.send_json(self.app.jobs.submit(request))
                return
            self.send_error(HTTPStatus.NOT_FOUND)
        except (ValueError, KeyError, FileNotFoundError) as exc:
            self.send_json({"error": str(exc)}, 400)
        except RuntimeError as exc:
            self.send_json({"error": str(exc)}, 409)
        except Exception as exc:
            traceback.print_exc()
            self.send_json({"error": str(exc)}, 500)


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], domain_id: int, dry_run: bool):
        self.state = DashboardState()
        self.jobs = JobManager(MotionLibrary(MOTION_DIR), self.state, domain_id, dry_run)
        super().__init__(address, AppHandler)


def main() -> None:
    parser = argparse.ArgumentParser(description="해커톤 양산 로봇 대시보드")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--domain-id", type=int, default=21)
    parser.add_argument("--dry-run", action="store_true", help="phorce play 없이 UI만 시험")
    args = parser.parse_args()
    server = DashboardServer((args.host, args.port), args.domain_id, args.dry_run)
    print(f"Umbrella dashboard: http://127.0.0.1:{args.port} "
          f"({'DRY RUN' if args.dry_run else 'ROBOT LIVE'})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
