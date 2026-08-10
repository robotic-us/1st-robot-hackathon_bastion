#!/usr/bin/env python3
"""Capture the current operational axes and stream that pose as relative zero."""

import time

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy

from agx_msgs.msg import PhorceCommand, PhorceFeedback


class RelativeZeroHold(Node):
    def __init__(self) -> None:
        super().__init__("relative_zero_hold")
        self.zero = None
        self.valid_mask = 0
        self.last_log = 0.0

        feedback_qos = QoSProfile(
            depth=1,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
        )
        command_qos = QoSProfile(
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
        )
        self.create_subscription(
            PhorceFeedback, "/phorce/feedback", self.on_feedback, feedback_qos
        )
        self.publisher = self.create_publisher(
            PhorceCommand, "/phorce_monitor/cmd", command_qos
        )
        self.create_timer(0.005, self.publish_hold)  # 200 Hz; source lease is 10 ms.
        self.get_logger().info("waiting for a fresh operational feedback frame")

    def on_feedback(self, msg: PhorceFeedback) -> None:
        if self.zero is not None or len(msg.axis) != 12:
            return
        mask = int(msg.axis_oper_mask)
        if mask == 0 or int(msg.axis_valid_mask) != mask or int(msg.axis_fault_mask) != 0:
            return
        if any(((mask >> i) & 1) and not msg.axis[i].valid for i in range(12)):
            return

        self.valid_mask = mask
        self.zero = [float(msg.axis[i].position_rad) if (mask >> i) & 1 else 0.0
                     for i in range(12)]
        values = ", ".join(
            f"a{i}={self.zero[i]:+.4f}" for i in range(12) if (mask >> i) & 1
        )
        self.get_logger().info(f"captured relative zero mask=0x{mask:03X}: {values}")
        self.get_logger().info("streaming HOLD only; arm/confirm are still required")

    def publish_hold(self) -> None:
        if self.zero is None:
            return
        msg = PhorceCommand()
        msg.stamp = self.get_clock().now().to_msg()
        msg.position_rad = list(self.zero)
        msg.torque_nm = [0.0] * 12
        msg.kd2 = [0.0] * 12
        self.publisher.publish(msg)

        now = time.monotonic()
        if now - self.last_log >= 2.0:
            self.last_log = now
            self.get_logger().info(f"holding relative zero at 200 Hz, mask=0x{self.valid_mask:03X}")


def main() -> None:
    rclpy.init()
    node = RelativeZeroHold()
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
