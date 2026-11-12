#!/usr/bin/env python3
"""Remove the robot body from a world-frame registered point cloud."""
import math
import time
from collections import deque

import numpy as np
import rclpy
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import PointCloud2, PointField
import tf2_ros


class PointCloudSelfFilter(Node):
    def __init__(self):
        super().__init__('pointcloud_self_filter')
        self.declare_parameter('input_topic', '/cloud_registered_full')
        self.declare_parameter('output_topic', '/cloud_registered_filtered')
        self.declare_parameter('body_frame', 'body')
        self.declare_parameter('min_x', -0.45)
        self.declare_parameter('max_x', 0.45)
        self.declare_parameter('min_y', -0.45)
        self.declare_parameter('max_y', 0.45)
        self.declare_parameter('min_z', -0.30)
        self.declare_parameter('max_z', 1.20)
        self.declare_parameter('transform_timeout', 0.05)
        self.body_frame = str(self.get_parameter('body_frame').value)
        self.bounds = np.asarray([
            float(self.get_parameter('min_x').value), float(self.get_parameter('max_x').value),
            float(self.get_parameter('min_y').value), float(self.get_parameter('max_y').value),
            float(self.get_parameter('min_z').value), float(self.get_parameter('max_z').value),
        ], dtype=np.float32)
        if not (self.bounds[0] < self.bounds[1] and self.bounds[2] < self.bounds[3] and
                self.bounds[4] < self.bounds[5] and np.all(np.isfinite(self.bounds))):
            raise ValueError('Invalid pointcloud self-filter bounds')
        self.timeout = max(0.0, float(self.get_parameter('transform_timeout').value))
        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)
        self.publisher = self.create_publisher(
            PointCloud2, str(self.get_parameter('output_topic').value), qos_profile_sensor_data)
        self.subscription = self.create_subscription(
            PointCloud2, str(self.get_parameter('input_topic').value), self.callback,
            qos_profile_sensor_data)
        self.warned = False
        self.pending_clouds = deque(maxlen=3)
        # Both callbacks use the default mutually exclusive group; only TF
        # reception runs concurrently, so queue access and filtering stay serial.
        self.pending_timer = self.create_timer(0.005, self._process_pending)

    @staticmethod
    def _xyz_array(message):
        fields = {field.name: field for field in message.fields}
        xyz = [fields.get(name) for name in ('x', 'y', 'z')]
        if any(field is None or field.datatype != PointField.FLOAT32 or field.count != 1
               or field.offset + 4 > message.point_step for field in xyz):
            raise ValueError('PointCloud2 requires scalar FLOAT32 x/y/z fields')
        if not message.height or not message.width:
            return np.empty((0, 3), dtype=np.float32)
        if message.row_step < message.width * message.point_step or len(message.data) < message.height * message.row_step:
            raise ValueError('Truncated PointCloud2')
        endian = '>f4' if message.is_bigendian else '<f4'
        columns = [np.ndarray((message.height, message.width), dtype=endian,
                              buffer=message.data, offset=field.offset,
                              strides=(message.row_step, message.point_step)).reshape(-1)
                   for field in xyz]
        points = np.column_stack(columns).astype(np.float32, copy=False)
        return points

    @staticmethod
    def _matrix(transform):
        t, q = transform.transform.translation, transform.transform.rotation
        norm = math.sqrt(q.w * q.w + q.x * q.x + q.y * q.y + q.z * q.z)
        if not math.isfinite(norm) or norm < 1.0e-9:
            raise ValueError('Invalid TF quaternion')
        w, x, y, z = q.w / norm, q.x / norm, q.y / norm, q.z / norm
        return np.array([
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w), t.x],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w), t.y],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y), t.z],
        ], dtype=np.float32)

    def callback(self, message):
        self.pending_clouds.append((message, time.monotonic()))
        self._process_pending()

    def _process_pending(self):
        while self.pending_clouds:
            message, queued_at = self.pending_clouds[0]
            if self.timeout > 0 and time.monotonic() - queued_at >= self.timeout:
                self.pending_clouds.popleft()
                if not self.warned:
                    self.get_logger().warning('Skipping cloud: TF wait budget expired')
                    self.warned = True
                continue
            try:
                requested_time = rclpy.time.Time.from_msg(message.header.stamp)
                # Nonblocking lookup: leave this frame queued while TF catches
                # up, instead of sleeping inside the executor callback.
                transform = self.tf_buffer.lookup_transform(
                    self.body_frame, message.header.frame_id, requested_time)
                self._filter_cloud(message, transform)
                self.warned = False
            except (tf2_ros.TransformException, ValueError) as error:
                if (isinstance(error, tf2_ros.TransformException) and
                        time.monotonic() - queued_at < self.timeout):
                    return
                if not self.warned:
                    self.get_logger().warning(
                        f'Skipping cloud until body TF/filter input is valid: {error}')
                    self.warned = True
            self.pending_clouds.popleft()

    def _filter_cloud(self, message, transform):
        matrix = self._matrix(transform)
        points = self._xyz_array(message)
        finite = np.all(np.isfinite(points), axis=1)
        body_points = points[finite] @ matrix[:, :3].T + matrix[:, 3]
        inside = ((body_points[:, 0] >= self.bounds[0]) & (body_points[:, 0] <= self.bounds[1]) &
                  (body_points[:, 1] >= self.bounds[2]) & (body_points[:, 1] <= self.bounds[3]) &
                  (body_points[:, 2] >= self.bounds[4]) & (body_points[:, 2] <= self.bounds[5]))
        keep = finite.copy()
        keep[finite] = ~inside
        # Select whole point records, including fields/padding unknown to
        # this filter. Respect row padding in organized input clouds.
        records = np.ndarray(
            (message.height, message.width), dtype=np.dtype((np.void, message.point_step)),
            buffer=message.data, strides=(message.row_step, message.point_step))
        data = records.reshape(-1)[keep].tobytes()
        width = int(np.count_nonzero(keep))
        self.publisher.publish(PointCloud2(
            header=message.header, height=1, width=width, fields=message.fields,
            is_bigendian=message.is_bigendian, point_step=message.point_step,
            row_step=width * message.point_step, data=data, is_dense=message.is_dense))


def main(args=None):
    rclpy.init(args=args)
    node = PointCloudSelfFilter()
    executor = MultiThreadedExecutor(num_threads=2)
    executor.add_node(node)
    try:
        executor.spin()
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
