from __future__ import annotations

import json
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ament_index_python.packages import get_package_share_directory
from python_qt_binding.QtCore import QObject, QTimer, Signal
from python_qt_binding.QtGui import QDoubleValidator
from python_qt_binding.QtWidgets import (
    QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QWidget,
)
from qt_gui.plugin import Plugin

from .solar import select_motion, solar_elevation


class _WorkerSignals(QObject):
    finished = Signal(str)


class UmbrellaControlPlugin(Plugin):
    def __init__(self, context):
        super().__init__(context)
        self.setObjectName("UmbrellaControlPlugin")
        self._config = self._load_config()
        self._busy = False
        self._signals = _WorkerSignals()
        self._signals.finished.connect(self._play_finished)

        self._widget = QWidget()
        self._widget.setWindowTitle("PhORCE 양산 제어")
        layout = QVBoxLayout(self._widget)

        person = QGroupBox("사람 정보")
        person_form = QFormLayout(person)
        self._height = QLineEdit("170")
        self._height.setValidator(QDoubleValidator(80.0, 250.0, 1, self._height))
        self._height.setPlaceholderText("80–250")
        person_form.addRow("사람 키 (cm)", self._height)
        layout.addWidget(person)

        sun = QGroupBox("현재 태양 고도 기반 양산 모션")
        sun_form = QFormLayout(sun)
        self._time_label = QLabel("-")
        self._elevation_label = QLabel("-")
        self._selection_label = QLabel("-")
        self._selection_label.setWordWrap(True)
        sun_form.addRow("기준 시각", self._time_label)
        sun_form.addRow("태양 고도", self._elevation_label)
        sun_form.addRow("선택 결과", self._selection_label)
        refresh = QPushButton("현재 고도로 다시 선택")
        refresh.clicked.connect(self.refresh_sun)
        sun_form.addRow(refresh)
        layout.addWidget(sun)

        tests = QGroupBox("테스트 모션 (실물 실행)")
        test_layout = QHBoxLayout(tests)
        self._test_buttons = []
        for motion_id in (1, 2, 3):
            button = QPushButton(f"Motion {motion_id}")
            button.clicked.connect(lambda _checked=False, mid=motion_id: self.play_test_motion(mid))
            test_layout.addWidget(button)
            self._test_buttons.append(button)
        layout.addWidget(tests)

        self._status = QLabel("준비됨 · 움직이기 전 주변과 E-Stop을 확인하세요.")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        layout.addStretch(1)

        context.add_widget(self._widget)
        self.refresh_sun()
        self._timer = QTimer(self._widget)
        self._timer.timeout.connect(self.refresh_sun)
        self._timer.start(60_000)

    @staticmethod
    def _load_config():
        share = Path(get_package_share_directory("umbrella_control_rqt"))
        with (share / "config" / "umbrella_motions.json").open(encoding="utf-8") as handle:
            return json.load(handle)

    def refresh_sun(self):
        location = self._config["location"]
        now = datetime.now(ZoneInfo(location["timezone"]))
        elevation = solar_elevation(now, location["latitude_deg"], location["longitude_deg"])
        selected = select_motion(elevation, self._config["motions"])
        self._time_label.setText(now.strftime("%Y-%m-%d %H:%M:%S %Z"))
        self._elevation_label.setText(f"{elevation:.2f}°")
        if selected is None:
            self._selection_label.setText("해당 고도 구간 없음")
        elif selected.get("motion_id") is None:
            self._selection_label.setText(f"{selected['name']} · 모션 번호 미배정")
        else:
            self._selection_label.setText(f"{selected['name']} · Motion {selected['motion_id']}")

    def play_test_motion(self, motion_id: int):
        if self._busy:
            return
        height = self._height.text().strip()
        if not self._height.hasAcceptableInput():
            self._status.setText("사람 키를 80–250 cm 범위로 입력하세요.")
            return
        self._busy = True
        for button in self._test_buttons:
            button.setEnabled(False)
        self._status.setText(f"Motion {motion_id} 실행 중… (사람 키 {height} cm)")
        threading.Thread(target=self._play_worker, args=(motion_id,), daemon=True).start()

    def _play_worker(self, motion_id: int):
        try:
            proc = subprocess.run(
                ["phorce", "play", str(motion_id), "--target", "robot", "--timeout", "60", "--json"],
                capture_output=True, text=True, timeout=70, check=False,
            )
            raw = proc.stdout.strip() or proc.stderr.strip()
            try:
                detail = json.loads(raw).get("detail", raw)
            except json.JSONDecodeError:
                detail = raw
            ok = proc.returncode == 0
            message = f"Motion {motion_id} 완료" if ok else f"Motion {motion_id} 실패: {detail}"
        except Exception as exc:
            message = f"Motion {motion_id} 실행 오류: {exc}"
        self._signals.finished.emit(message)

    def _play_finished(self, message: str):
        self._busy = False
        for button in self._test_buttons:
            button.setEnabled(True)
        self._status.setText(message)

    def shutdown_plugin(self):
        self._timer.stop()
