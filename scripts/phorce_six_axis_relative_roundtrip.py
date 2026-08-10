#!/usr/bin/env python3
"""Move every operational PhORCE axis by a relative angle, then return."""

from __future__ import annotations

import argparse
import math
import time

import rclpy
from agx_msgs.msg import PhorceCommand, PhorceFeedback, PhorceStatus
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from std_srvs.srv import Trigger


EXPECTED_MASK = 0x01C7
NUM_AXES = 12


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--degrees", type=float, default=30.0)
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--hold", type=float, default=2.0)
    parser.add_argument("--rate", type=float, default=200.0)
    args = parser.parse_args()
    if not math.isfinite(args.degrees) or abs(args.degrees) > 30.0:
        parser.error("--degrees must be finite and within +/-30")
    if not math.isfinite(args.duration) or args.duration < 5.0:
        parser.error("--duration must be finite and at least 5 seconds")
    if not math.isfinite(args.hold) or args.hold < 0.0:
        parser.error("--hold must be non-negative and finite")
    if not math.isfinite(args.rate) or args.rate < 200.0:
        parser.error("--rate must be at least 200 Hz")
    return args


class SixAxisRoundTrip(Node):
    def __init__(self) -> None:
        super().__init__("phorce_six_axis_relative_roundtrip")
        self.feedback: PhorceFeedback | None = None
        self.status: PhorceStatus | None = None
        best_effort = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
        )
        reliable = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
        )
        self.create_subscription(PhorceFeedback, "/phorce/feedback", self._feedback, best_effort)
        self.create_subscription(PhorceStatus, "/phorce/status", self._status, best_effort)
        self.publisher = self.create_publisher(PhorceCommand, "/phorce_monitor/cmd", reliable)

    def _feedback(self, msg: PhorceFeedback) -> None:
        self.feedback = msg

    def _status(self, msg: PhorceStatus) -> None:
        self.status = msg

    def spin_until_ready(self, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        while rclpy.ok() and (self.feedback is None or self.status is None):
            if time.monotonic() >= deadline:
                raise RuntimeError("fresh feedback/status timeout")
            rclpy.spin_once(self, timeout_sec=0.05)
        self.check_health(require_active=False)

    def check_health(self, require_active: bool) -> None:
        fb, status = self.feedback, self.status
        if fb is None or status is None:
            raise RuntimeError("feedback/status unavailable")
        if int(fb.axis_oper_mask) != EXPECTED_MASK:
            raise RuntimeError(f"unexpected operational mask 0x{int(fb.axis_oper_mask):03X}")
        if int(fb.axis_valid_mask) != EXPECTED_MASK or int(fb.axis_stale_mask):
            raise RuntimeError("axis feedback invalid or stale")
        if int(fb.axis_fault_mask) or int(status.axis_fault_mask):
            raise RuntimeError(f"axis fault 0x{int(fb.axis_fault_mask):03X}")
        if status.estop_active or not status.ethercat_operational or int(status.wkc_err):
            raise RuntimeError("EtherCAT/WKC/E-stop health check failed")
        if int(status.echo_lag_strikes):
            raise RuntimeError(f"echo lag strike count={int(status.echo_lag_strikes)}")
        if require_active and int(status.master_state) != 4:
            raise RuntimeError(f"ACTIVE lost: master_state={int(status.master_state)}")

    def trigger(self, name: str) -> None:
        client = self.create_client(Trigger, name)
        if not client.wait_for_service(timeout_sec=3.0):
            raise RuntimeError(f"service unavailable: {name}")
        future = client.call_async(Trigger.Request())
        while rclpy.ok() and not future.done():
            rclpy.spin_once(self, timeout_sec=0.02)
        response = future.result()
        if response is None or not response.success:
            raise RuntimeError(f"{name} failed: {getattr(response, 'message', 'no response')}")
        print(f"{name}: {response.message}", flush=True)

    def publish(self, positions: list[float]) -> None:
        msg = PhorceCommand()
        msg.stamp = self.get_clock().now().to_msg()
        msg.position_rad = list(positions)
        msg.torque_nm = [0.0] * NUM_AXES
        msg.kd2 = [0.0] * NUM_AXES
        self.publisher.publish(msg)

    def stream_constant(self, positions: list[float], seconds: float, active: bool) -> None:
        self.stream_curve(positions, positions, seconds, active)

    def stream_curve(self, start: list[float], goal: list[float], seconds: float, active: bool) -> None:
        period = 0.005
        begun = time.monotonic()
        next_tick = begun
        while rclpy.ok():
            now = time.monotonic()
            u = min((now - begun) / max(seconds, period), 1.0)
            # Quintic smoothstep: zero velocity and acceleration at both ends.
            s = u * u * u * (10.0 + u * (-15.0 + 6.0 * u))
            command = [a + s * (b - a) for a, b in zip(start, goal)]
            self.publish(command)
            rclpy.spin_once(self, timeout_sec=0.0)
            self.check_health(require_active=active)
            if u >= 1.0:
                return
            next_tick += period
            time.sleep(max(0.0, next_tick - time.monotonic()))


def main() -> None:
    args = arguments()
    rclpy.init()
    node = SixAxisRoundTrip()
    try:
        node.spin_until_ready()
        assert node.feedback is not None
        zero = [float(axis.position_rad) for axis in node.feedback.axis]
        if len(zero) != NUM_AXES or not all(math.isfinite(value) for value in zero):
            raise RuntimeError("invalid captured positions")
        delta = math.radians(args.degrees)
        goal = [value + delta if (EXPECTED_MASK >> i) & 1 else value for i, value in enumerate(zero)]
        print("relative zero: " + ", ".join(
            f"a{i}={math.degrees(zero[i]):+.2f}deg" for i in range(NUM_AXES) if (EXPECTED_MASK >> i) & 1
        ), flush=True)
        print(f"pre-streaming HOLD, then all six axes {args.degrees:+.1f}deg and return", flush=True)

        node.stream_constant(zero, 1.5, active=False)
        node.trigger("/phorce_monitor/arm")
        node.trigger("/phorce_monitor/confirm")

        active_deadline = time.monotonic() + 1.0
        while rclpy.ok() and (node.status is None or int(node.status.master_state) != 4):
            node.publish(zero)
            rclpy.spin_once(node, timeout_sec=0.005)
            if time.monotonic() >= active_deadline:
                raise RuntimeError("ACTIVE transition timeout")
        node.stream_constant(zero, 2.0, active=True)

        print(f"moving outbound over {args.duration:.1f}s", flush=True)
        node.stream_curve(zero, goal, args.duration, active=True)
        node.stream_constant(goal, args.hold, active=True)
        assert node.feedback is not None
        outbound = [float(axis.position_rad) for axis in node.feedback.axis]
        outbound_moves = [
            math.degrees(outbound[i] - zero[i])
            for i in range(NUM_AXES) if (EXPECTED_MASK >> i) & 1
        ]
        print(
            "outbound measured moves: "
            + ", ".join(f"{move:+.3f}deg" for move in outbound_moves),
            flush=True,
        )
        reached_goal = all(abs(move - args.degrees) <= 2.0 for move in outbound_moves)
        print(f"returning to relative zero over {args.duration:.1f}s", flush=True)
        node.stream_curve(goal, zero, args.duration, active=True)
        node.stream_constant(zero, 3.0, active=True)

        assert node.feedback is not None
        final = [float(axis.position_rad) for axis in node.feedback.axis]
        errors = [math.degrees(final[i] - zero[i]) for i in range(NUM_AXES) if (EXPECTED_MASK >> i) & 1]
        print("round trip complete; final relative errors: " + ", ".join(f"{e:+.3f}deg" for e in errors), flush=True)
        if not reached_goal:
            raise RuntimeError("one or more axes did not reach the +30deg endpoint within 2deg")
    except Exception as exc:
        print(f"ABORT: {exc}; command publication is stopping", flush=True)
        raise SystemExit(1) from exc
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
