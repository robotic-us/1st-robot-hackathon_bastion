#!/usr/bin/env python3
"""Real-time multi-axis relative-zero frontend for PhorceCommand.

The PCM wire contract is absolute-position based.  This node captures a zero
snapshot from feedback and continuously converts relative degree targets to the
absolute radians expected by /phorce_monitor/cmd.  It never uses motion slots.
"""

from __future__ import annotations

import math
import time

import rclpy
from agx_msgs.msg import PhorceCommand, PhorceFeedback
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import Float64MultiArray
from std_srvs.srv import Trigger


NUM_AXES = 12
DEFAULT_MASK = 0x01C7


def absolute_positions(
    zero: list[float], relative: list[float], active_axes: list[int]
) -> list[float]:
    """Convert relative radians to the 12-axis absolute command vector."""
    result = [0.0] * NUM_AXES
    for axis in active_axes:
        result[axis] = zero[axis] + relative[axis]
    return result


class RelativeController(Node):
    def __init__(self) -> None:
        super().__init__("phorce_relative_controller")

        self.declare_parameter("axes_mask", DEFAULT_MASK)
        self.declare_parameter("rate_hz", 200.0)
        self.declare_parameter("max_speed_deg_s", 30.0)
        self.declare_parameter("max_relative_deg", 180.0)

        self.axes_mask = int(self.get_parameter("axes_mask").value)
        self.rate_hz = float(self.get_parameter("rate_hz").value)
        self.max_speed_rad_s = math.radians(
            float(self.get_parameter("max_speed_deg_s").value)
        )
        self.max_relative_rad = math.radians(
            float(self.get_parameter("max_relative_deg").value)
        )
        if not 0 < self.axes_mask < (1 << NUM_AXES):
            raise ValueError("axes_mask must be a nonzero 12-bit mask")
        if not math.isfinite(self.rate_hz) or self.rate_hz < 200.0:
            raise ValueError("rate_hz must be at least 200")
        if not math.isfinite(self.max_speed_rad_s) or self.max_speed_rad_s <= 0.0:
            raise ValueError("max_speed_deg_s must be positive")
        if not math.isfinite(self.max_relative_rad) or self.max_relative_rad <= 0.0:
            raise ValueError("max_relative_deg must be positive")

        self.active_axes = [i for i in range(NUM_AXES) if (self.axes_mask >> i) & 1]
        self.feedback: PhorceFeedback | None = None
        self.zero: list[float] | None = None
        self.command_rel = [0.0] * NUM_AXES
        self.target_rel = [0.0] * NUM_AXES
        self.motion_enabled = False
        self.last_tick = time.monotonic()
        self.last_feedback_time = 0.0

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
        self.create_subscription(
            PhorceFeedback, "/phorce/feedback", self._on_feedback, feedback_qos
        )
        self.create_subscription(
            Float64MultiArray,
            "/phorce_relative/target_deg",
            self._on_target,
            command_qos,
        )
        self.publisher = self.create_publisher(
            PhorceCommand, "/phorce_monitor/cmd", command_qos
        )
        self.create_service(Trigger, "/phorce_relative/set_zero", self._set_zero)
        self.create_service(Trigger, "/phorce_relative/enable", self._enable)
        self.create_service(Trigger, "/phorce_relative/disable", self._disable)
        self.create_timer(1.0 / self.rate_hz, self._tick)

        self.get_logger().info(
            f"relative controller ready: axes=0x{self.axes_mask:03X} "
            f"order={self.active_axes}, rate={self.rate_hz:.0f}Hz"
        )

    def _feedback_healthy(self, msg: PhorceFeedback) -> tuple[bool, str]:
        if len(msg.axis) != NUM_AXES:
            return False, f"expected 12 axes, got {len(msg.axis)}"
        oper_mask = int(msg.axis_oper_mask)
        valid_mask = int(msg.axis_valid_mask)
        stale_mask = int(msg.axis_stale_mask)
        fault_mask = int(msg.axis_fault_mask)
        if (oper_mask & self.axes_mask) != self.axes_mask:
            return False, (
                f"controlled axes 0x{self.axes_mask:03X} are not all operational "
                f"(oper=0x{oper_mask:03X})"
            )
        if (valid_mask & self.axes_mask) != self.axes_mask or (stale_mask & self.axes_mask):
            return False, "controlled-axis feedback invalid/stale"
        if fault_mask & self.axes_mask:
            return False, f"controlled-axis fault mask=0x{fault_mask & self.axes_mask:03X}"
        if any(not math.isfinite(float(msg.axis[i].position_rad)) for i in self.active_axes):
            return False, "non-finite axis position"
        return True, "ok"

    def _capture_zero(self) -> tuple[bool, str]:
        if self.feedback is None:
            return False, "feedback not received"
        healthy, reason = self._feedback_healthy(self.feedback)
        if not healthy:
            return False, reason
        self.zero = [
            float(self.feedback.axis[i].position_rad) if i in self.active_axes else 0.0
            for i in range(NUM_AXES)
        ]
        self.command_rel = [0.0] * NUM_AXES
        self.target_rel = [0.0] * NUM_AXES
        values = ", ".join(
            f"a{i}={math.degrees(self.zero[i]):+.3f}deg" for i in self.active_axes
        )
        self.get_logger().info(f"relative zero captured: {values}")
        return True, f"zero captured for axes {self.active_axes}"

    def _on_feedback(self, msg: PhorceFeedback) -> None:
        self.feedback = msg
        self.last_feedback_time = time.monotonic()
        if self.zero is None:
            self._capture_zero()

    def _on_target(self, msg: Float64MultiArray) -> None:
        values = [float(value) for value in msg.data]
        if len(values) == len(self.active_axes):
            pairs = zip(self.active_axes, values)
        elif len(values) == NUM_AXES:
            pairs = ((i, values[i]) for i in self.active_axes)
        else:
            self.get_logger().error(
                f"target rejected: need {len(self.active_axes)} or 12 values, got {len(values)}"
            )
            return

        candidate = list(self.target_rel)
        for axis, degrees in pairs:
            radians = math.radians(degrees)
            if not math.isfinite(radians) or abs(radians) > self.max_relative_rad:
                self.get_logger().error(
                    f"target rejected: a{axis}={degrees}deg exceeds finite "
                    f"+/-{math.degrees(self.max_relative_rad):.1f}deg"
                )
                return
            candidate[axis] = radians
        self.target_rel = candidate
        summary = ", ".join(
            f"a{i}={math.degrees(candidate[i]):+.2f}deg" for i in self.active_axes
        )
        self.get_logger().info(f"new relative target: {summary}")

    def _set_zero(self, _request: Trigger.Request, response: Trigger.Response) -> Trigger.Response:
        if self.motion_enabled:
            response.success = False
            response.message = "disable motion before changing zero"
            return response
        response.success, response.message = self._capture_zero()
        return response

    def _enable(self, _request: Trigger.Request, response: Trigger.Response) -> Trigger.Response:
        if self.zero is None or self.feedback is None:
            response.success = False
            response.message = "zero/feedback unavailable"
            return response
        healthy, reason = self._feedback_healthy(self.feedback)
        if not healthy:
            response.success = False
            response.message = reason
            return response
        self.motion_enabled = True
        response.success = True
        response.message = "relative targets enabled; HOLD stream remains continuous"
        return response

    def _disable(self, _request: Trigger.Request, response: Trigger.Response) -> Trigger.Response:
        self.motion_enabled = False
        self.target_rel = list(self.command_rel)
        response.success = True
        response.message = "relative motion frozen at current command"
        return response

    def _tick(self) -> None:
        now = time.monotonic()
        dt = min(max(now - self.last_tick, 0.0), 0.02)
        self.last_tick = now
        if self.zero is None or self.feedback is None:
            return
        healthy, reason = self._feedback_healthy(self.feedback)
        if not healthy or now - self.last_feedback_time >= 0.05:
            if self.motion_enabled:
                self.get_logger().error(f"motion disabled: {reason}")
            self.motion_enabled = False
            return

        if self.motion_enabled:
            max_step = self.max_speed_rad_s * dt
            for axis in self.active_axes:
                error = self.target_rel[axis] - self.command_rel[axis]
                self.command_rel[axis] += max(-max_step, min(max_step, error))

        command = PhorceCommand()
        command.stamp = self.get_clock().now().to_msg()
        command.position_rad = absolute_positions(
            self.zero, self.command_rel, self.active_axes
        )
        command.torque_nm = [0.0] * NUM_AXES
        command.kd2 = [0.0] * NUM_AXES
        self.publisher.publish(command)


def main() -> None:
    rclpy.init()
    node = RelativeController()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
