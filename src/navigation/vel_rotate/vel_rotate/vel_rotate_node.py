#!/usr/bin/env python3
"""Convert world-aligned MPC translation using the received big-gimbal angle."""

import math
import time

from example_interfaces.msg import Float32
from geometry_msgs.msg import Twist
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rm_interfaces.msg import SerialReceiveData


class VelRotate(Node):
    def __init__(self):
        super().__init__('vel_rotate')
        self.declare_parameter('init_spin_speed', 0.0)
        self.declare_parameter('timeout_sec', 0.25)
        self.spin_speed = self.get_parameter('init_spin_speed').value
        self.timeout_sec = self.get_parameter('timeout_sec').value
        if not math.isfinite(self.spin_speed) or not math.isfinite(self.timeout_sec) or self.timeout_sec <= 0:
            raise ValueError('init_spin_speed must be finite and timeout_sec must be positive')

        self.angle_rad = None
        self.last_feedback_time = None
        self.last_command_time = None
        self.publisher = self.create_publisher(
            Twist, '/cmd_vel_rotate', qos_profile_sensor_data)
        self.create_subscription(
            SerialReceiveData, '/serial/receive', self.on_feedback, qos_profile_sensor_data)
        self.create_subscription(
            Twist, '/cmd_vel_mpc', self.on_command, qos_profile_sensor_data)
        self.create_subscription(
            Float32, '/cmd_spin', self.on_spin, qos_profile_sensor_data)
        self.create_timer(0.05, self.check_timeout)

    def on_feedback(self, message):
        if not math.isfinite(message.big_yaw):
            self.angle_rad = None
            self.last_feedback_time = None
            self.publisher.publish(Twist())
            return
        self.angle_rad = math.radians(message.big_yaw)
        self.last_feedback_time = time.monotonic()

    def on_spin(self, message):
        if math.isfinite(message.data):
            self.spin_speed = message.data

    def on_command(self, message):
        now = time.monotonic()
        self.last_command_time = now
        if (self.angle_rad is None or self.last_feedback_time is None or
                now - self.last_feedback_time > self.timeout_sec or
                not all(math.isfinite(value) for value in (
                    message.linear.x, message.linear.y, message.angular.z))):
            self.publisher.publish(Twist())
            return

        cosine = math.cos(self.angle_rad)
        sine = math.sin(self.angle_rad)
        output = Twist()
        output.linear.x = message.linear.x * cosine - message.linear.y * sine
        output.linear.y = message.linear.x * sine + message.linear.y * cosine
        output.angular.z = message.angular.z + self.spin_speed
        self.publisher.publish(output)

    def check_timeout(self):
        now = time.monotonic()
        if (self.last_feedback_time is None or self.last_command_time is None or
                now - self.last_feedback_time > self.timeout_sec or
                now - self.last_command_time > self.timeout_sec):
            self.publisher.publish(Twist())


def main():
    rclpy.init()
    node = VelRotate()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if rclpy.ok():
            node.publisher.publish(Twist())
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
