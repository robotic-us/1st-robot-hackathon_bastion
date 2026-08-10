#!/usr/bin/env python3
"""Interactive eleven-level converging motion graph for PhORCE slots 1..30."""

from __future__ import annotations

import argparse
import json
import subprocess
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from tkinter import font as tkfont


BG = "#07090d"
PANEL = "#0d1118"
WHITE = "#f4f7fb"
MUTED = "#3d4652"
MUTED_TEXT = "#697483"
ACCENT = "#35d9ff"
ACCENT_FILL = "#123743"
SUCCESS = "#60e6a8"
ERROR = "#ff657a"

LEVELS = 11
GRAPH_WIDTH = 1000
GRAPH_HEIGHT = 1700
NODE_RADIUS = 12


@dataclass(frozen=True)
class Edge:
    motion_id: int
    parent: int
    child: int
    direction: str


def build_edges() -> list[Edge]:
    """Three choices connect each level to the same node on the next level."""
    edges: list[Edge] = []
    for parent in range(LEVELS - 1):
        # The base movement slots at the root are intentionally ordered as
        # 1=forward, 2=left, 3=right.  Later graph segments retain their
        # original left/forward/right ordering.
        directions = ("F", "L", "R") if parent == 0 else ("L", "F", "R")
        for offset, direction in enumerate(directions, start=1):
            motion_id = 3 * parent + offset
            edges.append(Edge(motion_id, parent, parent + 1, direction))
    return edges


def node_level(node_id: int) -> int:
    return node_id + 1


class MotionTreeApp:
    def __init__(self, root: tk.Tk, args: argparse.Namespace) -> None:
        self.root = root
        self.args = args
        self.edges = build_edges()
        self.available: set[int] = set()
        self.node_enabled: dict[int, bool] = {0: True}
        self.edge_enabled: dict[int, bool] = {}
        self.selected_edge: int | None = None
        self.running_motion: int | None = None
        self.graph_terminated = False
        # The physical wheel angles determine which layer may run next.
        # A fresh program starts at the 0-degree root and advances only after
        # an explicitly successful motion result.
        self.current_node = args.start_node

        root.title("PhORCE Motion Tree")
        root.configure(bg=BG)
        root.geometry("1100x930")
        root.minsize(900, 650)

        self.title_font = tkfont.Font(family="DejaVu Sans", size=17, weight="bold")
        self.label_font = tkfont.Font(family="DejaVu Sans", size=9, weight="bold")
        self.small_font = tkfont.Font(family="DejaVu Sans", size=9)

        self._build_toolbar()
        self._build_canvas()
        self._set_status("PCM 모션 목록을 확인하는 중…", WHITE)
        self.refresh_catalog()

    def _build_toolbar(self) -> None:
        bar = tk.Frame(self.root, bg=PANEL, padx=18, pady=12)
        bar.pack(fill="x")

        tk.Label(
            bar, text="MOTION GRAPH · 11 LEVELS", bg=PANEL, fg=WHITE,
            font=self.title_font,
        ).pack(side="left")

        self.refresh_button = tk.Button(
            bar, text="슬롯 새로고침", command=self.refresh_catalog,
            bg="#18202a", fg=WHITE, activebackground="#273443",
            activeforeground=WHITE, relief="flat", padx=14, pady=7,
            cursor="hand2",
        )
        self.refresh_button.pack(side="right")

        self.motion31_button = tk.Button(
            bar, text="31 · MD0 단독 테스트", command=self.play_motion31,
            bg="#18202a", fg=WHITE, activebackground="#273443",
            activeforeground=WHITE, disabledforeground=MUTED_TEXT,
            relief="flat", padx=14, pady=7, cursor="hand2", state="disabled",
        )
        self.motion31_button.pack(side="right", padx=(0, 8))

        self.status_label = tk.Label(
            bar, text="", bg=PANEL, fg=WHITE, font=self.small_font,
            padx=18, anchor="e",
        )
        self.status_label.pack(side="right", fill="x", expand=True)

    def _build_canvas(self) -> None:
        holder = tk.Frame(self.root, bg=BG)
        holder.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(
            holder, bg=BG, highlightthickness=0,
            scrollregion=(0, 0, GRAPH_WIDTH, GRAPH_HEIGHT),
        )
        hbar = tk.Scrollbar(holder, orient="horizontal", command=self.canvas.xview)
        vbar = tk.Scrollbar(holder, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=hbar.set, yscrollcommand=vbar.set)
        hbar.pack(side="bottom", fill="x")
        vbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self._initial_view_positioned = False
        self.canvas.bind("<Configure>", self._center_graph)

    def _center_graph(self, _event: tk.Event | None = None) -> None:
        viewport = max(self.canvas.winfo_width(), 1)
        if viewport < GRAPH_WIDTH:
            self.canvas.xview_moveto((GRAPH_WIDTH - viewport) / (2 * GRAPH_WIDTH))
        if not self._initial_view_positioned:
            self.canvas.yview_moveto(1.0)
            self._initial_view_positioned = True

    def _set_status(self, text: str, color: str = WHITE) -> None:
        self.status_label.configure(text=text, fg=color)

    def refresh_catalog(self) -> None:
        if self.running_motion is not None:
            return
        self.refresh_button.configure(state="disabled")
        self.motion31_button.configure(state="disabled")
        self._set_status("활성화된 모션 슬롯을 읽는 중…", WHITE)
        threading.Thread(target=self._catalog_worker, daemon=True).start()

    def _base_phorce_args(self) -> list[str]:
        result = ["--target", self.args.target, "--domain-id", str(self.args.domain_id)]
        if self.args.namespace:
            result.extend(("--namespace", self.args.namespace))
        return result

    def _catalog_worker(self) -> None:
        cmd = ["phorce", "list", *self._base_phorce_args(), "--timeout", "3", "--json"]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=6, check=False)
            payload = json.loads(proc.stdout.strip() or proc.stderr.strip())
            if proc.returncode != 0 or not payload.get("ok"):
                raise RuntimeError(payload.get("detail") or f"phorce list 종료 코드 {proc.returncode}")
            ids = {
                int(item["ms_id"])
                for item in payload.get("motions", [])
                if 1 <= int(item["ms_id"]) <= 31
            }
            self.root.after(0, lambda: self._catalog_ready(ids))
        except Exception as exc:  # GUI must remain usable when ROS is not running.
            self.root.after(0, lambda message=str(exc): self._catalog_failed(message))

    def _catalog_ready(self, ids: set[int]) -> None:
        self.available = ids
        self._compute_enabled_tree()
        self._draw()
        self.refresh_button.configure(state="normal")
        self.motion31_button.configure(state="normal" if 31 in ids else "disabled")
        graph_count = len(ids.intersection(range(1, 31)))
        self._set_status(
            f"그래프 슬롯 {graph_count}/30 · 현재 {self.current_node + 1}단의 다음 3개만 실행 가능",
            SUCCESS,
        )

    def _catalog_failed(self, message: str) -> None:
        self.available = set()
        self._compute_enabled_tree()
        self._draw()
        self.refresh_button.configure(state="normal")
        self.motion31_button.configure(state="disabled")
        self._set_status(f"PCM 목록 연결 실패 · {message}", ERROR)

    def _compute_enabled_tree(self) -> None:
        self.node_enabled = {0: True}
        self.edge_enabled = {}
        for parent in range(LEVELS - 1):
            parent_enabled = self.node_enabled.get(parent, False)
            group = self.edges[parent * 3:parent * 3 + 3]
            for edge in group:
                self.edge_enabled[edge.motion_id] = parent_enabled and edge.motion_id in self.available
            self.node_enabled[parent + 1] = any(
                self.edge_enabled[edge.motion_id] for edge in group
            )

    @staticmethod
    def _positions() -> dict[int, tuple[float, float]]:
        return {
            node_id: (GRAPH_WIDTH / 2, GRAPH_HEIGHT - 80 - node_id * 145)
            for node_id in range(LEVELS)
        }

    def _draw(self) -> None:
        self.canvas.delete("all")
        positions = self._positions()

        for node_id, (_x, y) in positions.items():
            self.canvas.create_text(
                32, y, text=f"{node_id + 1}단", anchor="w", fill=MUTED_TEXT,
                font=self.label_font,
            )

        for edge in self.edges:
            x1, y1 = positions[edge.parent]
            x2, y2 = positions[edge.child]
            enabled = self.edge_enabled.get(edge.motion_id, False)
            selected = edge.motion_id == self.selected_edge
            color = ACCENT if selected else (WHITE if enabled else MUTED)
            width = 3 if selected else 1.4
            tag = f"edge_{edge.motion_id}"

            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            curve_offset = {"L": -150, "F": 0, "R": 150}[edge.direction]
            points = (x1, y1, mx + curve_offset, my, x2, y2)
            # Wide invisible hit target under the visible curved line.
            self.canvas.create_line(
                *points, fill=BG, width=18, smooth=True, splinesteps=24, tags=(tag,)
            )
            self.canvas.create_line(
                *points, fill=color, width=width, smooth=True, splinesteps=24, tags=(tag,)
            )
            label_x = mx + curve_offset * 0.72
            self.canvas.create_rectangle(
                label_x - 14, my - 10, label_x + 14, my + 10,
                fill=BG, outline="", tags=(tag,),
            )
            self.canvas.create_text(
                label_x, my, text=str(edge.motion_id), fill=color,
                font=self.label_font, tags=(tag,),
            )
            selectable = (
                enabled
                and edge.parent == self.current_node
                and not self.graph_terminated
            )
            if selectable and self.running_motion is None:
                self.canvas.tag_bind(tag, "<Button-1>", lambda _e, mid=edge.motion_id: self.play(mid))
                self.canvas.tag_bind(tag, "<Enter>", lambda _e: self.canvas.configure(cursor="hand2"))
                self.canvas.tag_bind(tag, "<Leave>", lambda _e: self.canvas.configure(cursor=""))

        selected_nodes: set[int] = set()
        if self.selected_edge is not None:
            edge = self.edges[self.selected_edge - 1]
            selected_nodes = {edge.parent, edge.child}

        for node_id, (x, y) in positions.items():
            enabled = self.node_enabled.get(node_id, False)
            selected = node_id in selected_nodes
            outline = ACCENT if selected else (WHITE if enabled else MUTED)
            fill = ACCENT_FILL if selected else BG
            self.canvas.create_oval(
                x - NODE_RADIUS, y - NODE_RADIUS, x + NODE_RADIUS, y + NODE_RADIUS,
                fill=fill, outline=outline, width=3 if selected else 2,
            )

        self.canvas.create_text(
            GRAPH_WIDTH / 2, GRAPH_HEIGHT - 25,
            text=(
                f"현재 {self.current_node + 1}단 · 다음 3개 간선만 클릭 가능   |   "
                "첫 구간: 1 직진 · 2 좌회전 · 3 우회전   |   회색: 비활성 경로"
            ),
            fill=MUTED_TEXT, font=self.small_font,
        )

    def play(self, motion_id: int) -> None:
        edge = self.edges[motion_id - 1]
        if (
            self.running_motion is not None
            or not self.edge_enabled.get(motion_id, False)
            or edge.parent != self.current_node
        ):
            return
        self.selected_edge = motion_id
        self.running_motion = motion_id
        self._draw()
        self.refresh_button.configure(state="disabled")
        self.motion31_button.configure(state="disabled")
        self._set_status(f"Motion {motion_id} 실행 중…", ACCENT)
        threading.Thread(target=self._play_worker, args=(motion_id, True), daemon=True).start()

    def play_motion31(self) -> None:
        """Run the independent MD0 test without advancing the graph level."""
        if self.running_motion is not None or 31 not in self.available:
            return
        self.running_motion = 31
        self.refresh_button.configure(state="disabled")
        self.motion31_button.configure(state="disabled")
        self._set_status("Motion 31 · MD0 단독 테스트 실행 중…", ACCENT)
        threading.Thread(target=self._play_worker, args=(31, False), daemon=True).start()

    def _play_worker(self, motion_id: int, advance_graph: bool) -> None:
        cmd = [
            "phorce", "play", str(motion_id), *self._base_phorce_args(),
            "--timeout", str(self.args.play_timeout), "--json",
        ]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=self.args.play_timeout + 5, check=False,
            )
            raw = proc.stdout.strip() or proc.stderr.strip()
            payload = json.loads(raw) if raw else {}
            if proc.returncode != 0 or not payload.get("ok", False):
                detail = payload.get("detail") or payload.get("reason") or raw
                # Some PCM sessions transiently report Error 17 through the
                # Action result even though the same accepted request keeps
                # running and later reaches aggregate COMPLETED. Never resend
                # here: only reconcile the read-only final PCM state.
                if self._wait_for_pcm_completion(motion_id):
                    self.root.after(
                        0, lambda: self._play_finished(motion_id, None, advance_graph)
                    )
                    return
                raise RuntimeError(detail or f"종료 코드 {proc.returncode}")
            self.root.after(0, lambda: self._play_finished(motion_id, None, advance_graph))
        except Exception as exc:
            self.root.after(
                0,
                lambda message=str(exc): self._play_finished(
                    motion_id, message, advance_graph
                ),
            )

    def _wait_for_pcm_completion(self, motion_id: int) -> bool:
        """Reconcile a premature CLI failure without issuing another motion."""
        self.root.after(
            0,
            lambda: self._set_status(
                f"Motion {motion_id} 중간 오류 수신 · PCM 최종 상태 재확인 중…",
                ACCENT,
            ),
        )
        deadline = time.monotonic() + self.args.reconcile_timeout
        cmd = [
            "phorce", "status", *self._base_phorce_args(),
            "--timeout", "2", "--json",
        ]
        while time.monotonic() < deadline:
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=4, check=False)
                payload = json.loads(proc.stdout.strip() or proc.stderr.strip() or "{}")
                same_motion = int(payload.get("active_motion_id", 0)) == motion_id
                completed = payload.get("state_name") == "COMPLETED"
                safely_idle = bool(payload.get("physical_idle"))
                clean = int(payload.get("last_err", -1)) == 0
                if proc.returncode == 0 and same_motion and completed and safely_idle and clean:
                    return True
            except (OSError, ValueError, subprocess.SubprocessError):
                pass
            time.sleep(0.25)
        return False

    def _play_finished(
        self, motion_id: int, error: str | None, advance_graph: bool
    ) -> None:
        self.running_motion = None
        self.refresh_button.configure(state="normal")
        self.motion31_button.configure(
            state="normal" if 31 in self.available else "disabled"
        )
        self._draw()
        if error:
            self._set_status(f"Motion {motion_id} 실패 · {error}", ERROR)
        elif not advance_graph:
            self._set_status(
                f"Motion {motion_id} 완료 · 그래프는 {self.current_node + 1}단 유지",
                SUCCESS,
            )
        else:
            # Base differential turns no longer converge at +360 degrees:
            # left/right wheel groups finish at opposite absolute angles.
            # Opening the next tree layer would therefore run trajectories
            # whose starting angles do not match the robot.
            if motion_id in (2, 3):
                self.graph_terminated = True
                self._draw()
                self._set_status(
                    f"Motion {motion_id} 완료 · 좌우 절대각도 비수렴 · 다음 tree 구간 실행 금지",
                    SUCCESS,
                )
                return
            self.current_node = self.edges[motion_id - 1].child
            self._draw()
            if node_level(self.current_node) == LEVELS:
                self._set_status(f"Motion {motion_id} 완료 · 11단 경로 종료", SUCCESS)
            else:
                self._set_status(
                    f"Motion {motion_id} 완료 · 현재 {self.current_node + 1}단에서 다음 간선 선택",
                    SUCCESS,
                )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PhORCE 11-level converging motion graph GUI")
    parser.add_argument("--target", default="robot")
    parser.add_argument("--domain-id", type=int, default=21)
    parser.add_argument("--namespace", default=None)
    parser.add_argument("--play-timeout", type=float, default=30.0)
    parser.add_argument(
        "--reconcile-timeout", type=float, default=12.0,
        help="premature Action failure 뒤 PCM completion을 읽기만 하며 기다릴 시간",
    )
    parser.add_argument(
        "--start-node", type=int, default=0, choices=range(LEVELS),
        help="이미 완료한 물리 경로의 현재 단계 인덱스(0=1단, 1=2단)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = tk.Tk()
    MotionTreeApp(root, args)
    root.mainloop()


if __name__ == "__main__":
    main()
