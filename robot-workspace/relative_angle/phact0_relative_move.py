#!/usr/bin/env python3
"""Move phact0 by a relative angle using the absolute PhorceCommand API."""

from __future__ import annotations

import argparse
import math
import time

import rclpy
from agx_msgs.msg import PhorceCommand, PhorceFeedback
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)
from std_srvs.srv import Trigger


AXIS = 0  # phact0 / MD0 / node 0x02 / axis bit0
AXIS_BIT = 1 << AXIS
NUM_AXES = 12


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Move phact0 relative to its current feedback position."
    )
    parser.add_argument(
        "--degrees", type=float, default=10.0,
        help="relative motion in degrees (default: +10; use -10 for reverse)",
    )
    parser.add_argument(
        "--duration", type=float, default=3.0,
        help="motion duration in seconds (default: 3.0)",
    )
    parser.add_argument(
        "--hold", type=float, default=1.0,
        help="time to keep publishing the final target in seconds (default: 1.0)",
    )
    parser.add_argument(
        "--rate", type=float, default=200.0,
        help="command publication rate in Hz (default: 200)",
    )
    args = parser.parse_args()

    if not math.isfinite(args.degrees):
        parser.error("--degrees must be finite")
    if not math.isfinite(args.duration) or args.duration <= 0.0:
        parser.error("--duration must be positive and finite")
    if not math.isfinite(args.hold) or args.hold < 0.0:
        parser.error("--hold must be non-negative and finite")
    if not math.isfinite(args.rate) or args.rate < 100.0:
        parser.error("--rate must be at least 100 Hz (200 Hz is recommended)")
    return args


class RelativeMoveNode(Node):
    def __init__(self) -> None:
        super().__init__("phact0_relative_move")
        self.latest_feedback: PhorceFeedback | None = None

        feedback_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
        )
        command_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
        )
        self.subscription = self.create_subscription(
            PhorceFeedback,
            "/phorce/feedback",
            self._on_feedback,
            feedback_qos,
        )
        self.publisher = self.create_publisher(
            PhorceCommand,
            "/phorce_monitor/cmd",
            command_qos,
        )

    def _on_feedback(self, msg: PhorceFeedback) -> None:
        self.latest_feedback = msg

    def wait_for_feedback(self, timeout_sec: float = 5.0) -> PhorceFeedback:
        deadline = time.monotonic() + timeout_sec
        while rclpy.ok() and self.latest_feedback is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0.0:
                break
            rclpy.spin_once(self, timeout_sec=min(0.1, remaining))
        if self.latest_feedback is None:
            raise RuntimeError("/phorce/feedback was not received within 5 seconds")
        return self.latest_feedback

    def validate_phact0(self, feedback: PhorceFeedback) -> None:
        if not feedback.axis_valid_mask & AXIS_BIT:
            raise RuntimeError("phact0 feedback is not valid")
        if feedback.axis_stale_mask & AXIS_BIT:
            raise RuntimeError("phact0 feedback is stale")
        if not feedback.axis_oper_mask & AXIS_BIT:
            raise RuntimeError("phact0 is not operational")
        if feedback.axis_fault_mask & AXIS_BIT:
            raise RuntimeError("phact0 has a fault")
        if len(feedback.axis) != NUM_AXES:
            raise RuntimeError(f"expected {NUM_AXES} feedback axes, got {len(feedback.axis)}")

    def call_trigger(self, service_name: str) -> None:
        client = self.create_client(Trigger, service_name)
        if not client.wait_for_service(timeout_sec=3.0):
            raise RuntimeError(f"service not found: {service_name}")
        future = client.call_async(Trigger.Request())
        rclpy.spin_until_future_complete(self, future, timeout_sec=3.0)
        response = future.result()
        if response is None or not response.success:
            detail = response.message if response is not None else "no response"
            raise RuntimeError(f"{service_name} failed: {detail}")
        print(f"{service_name}: {response.message}")

    def publish_positions(self, positions: list[float]) -> None:
        msg = PhorceCommand()
        msg.stamp = self.get_clock().now().to_msg()
        msg.position_rad = positions
        msg.torque_nm = [0.0] * NUM_AXES
        msg.kd2 = [0.0] * NUM_AXES
        self.publisher.publish(msg)


def main() -> None:
    args = parse_args()
    rclpy.init()
    node = RelativeMoveNode()

    try:
        feedback = node.wait_for_feedback()
        node.validate_phact0(feedback)

        start = [axis.position_rad for axis in feedback.axis]
        if not all(math.isfinite(position) for position in start):
            raise RuntimeError("feedback contains a non-finite position")
        goal = start.copy()
        goal[AXIS] += math.radians(args.degrees)

        print(
            f"phact0: {math.degrees(start[AXIS]):.3f} deg -> "
            f"{math.degrees(goal[AXIS]):.3f} deg "
            f"(relative {args.degrees:+.3f} deg)"
        )

        node.call_trigger("/phorce_monitor/arm")
        node.call_trigger("/phorce_monitor/confirm")

        period = 1.0 / args.rate
        started_at = time.monotonic()
        next_publish = started_at

        while rclpy.ok():
            now = time.monotonic()
            u = min((now - started_at) / args.duration, 1.0)
            smooth = u * u * (3.0 - 2.0 * u)
            command = start.copy()
            command[AXIS] = start[AXIS] + smooth * (goal[AXIS] - start[AXIS])
            node.publish_positions(command)
            rclpy.spin_once(node, timeout_sec=0.0)

            if u >= 1.0:
                break
            next_publish += period
            time.sleep(max(0.0, next_publish - time.monotonic()))

        hold_until = time.monotonic() + args.hold
        while rclpy.ok() and time.monotonic() < hold_until:
            node.publish_positions(goal)
            rclpy.spin_once(node, timeout_sec=0.0)
            next_publish += period
            time.sleep(max(0.0, next_publish - time.monotonic()))

        print(f"phact0 relative move complete: {args.degrees:+.3f} deg")
    except KeyboardInterrupt:
        print("Interrupted; command publication stopped")
    except Exception as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(1) from exc
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
