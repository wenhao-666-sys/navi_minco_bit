"""Export a voxel PCD and its height projection in the SAME Point-LIO frame.

Like pcd2pgm, cells inside the projected bounding rectangle without obstacle
returns are free. Inspect the map before use; this is not visibility ray tracing
or a trajectory/loop-closure optimizer. The original SLAM mapping stays separate.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import signal
import sys

import numpy as np
import rclpy
from nav_msgs.msg import OccupancyGrid
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rclpy.signals import SignalHandlerOptions
from sensor_msgs.msg import PointCloud2, PointField
import tf2_ros

from mapping_grid_saver import write_grid


def read_xyz(msg):
    """Respect field offsets, byte order and organized-cloud row padding."""
    if not msg.height or not msg.width:
        return np.empty((0, 3), dtype=np.float32)
    fields = {field.name: field for field in msg.fields}
    xyz = [fields.get(name) for name in ('x', 'y', 'z')]
    if any(field is None or field.datatype != PointField.FLOAT32 or field.count != 1
           or field.offset < 0 or field.offset + 4 > msg.point_step for field in xyz):
        raise ValueError('Expected scalar FLOAT32 x/y/z fields')
    if msg.row_step < msg.width * msg.point_step or len(msg.data) < msg.height * msg.row_step:
        raise ValueError('Truncated PointCloud2 buffer')
    columns = [np.ndarray((msg.height, msg.width),
                          dtype='>f4' if msg.is_bigendian else '<f4',
                          buffer=msg.data, offset=field.offset,
                          strides=(msg.row_step, msg.point_step)).reshape(-1) for field in xyz]
    points = np.column_stack(columns)
    return points[np.all(np.isfinite(points), axis=1)]


def project_grid(points, resolution, ground_z, low, high):
    obstacles = points[(points[:, 2] >= ground_z + low) &
                       (points[:, 2] <= ground_z + high)]
    if len(obstacles) < 10:
        raise ValueError('Too few obstacle points in the ground-relative height band')
    cells = np.floor(obstacles[:, :2] / resolution).astype(np.int64)
    lower, upper = cells.min(axis=0) - 2, cells.max(axis=0) + 2
    width, height = (upper - lower + 1).tolist()
    if width * height > 16000000:
        raise ValueError('Projection exceeds 16 million cells; inspect Point-LIO outliers')
    data = np.zeros((height, width), dtype=np.int8)
    indices = cells - lower
    data[indices[:, 1], indices[:, 0]] = 100
    grid = OccupancyGrid()
    grid.header.frame_id = 'map'
    grid.info.resolution = resolution
    grid.info.width, grid.info.height = width, height
    grid.info.origin.position.x = float(lower[0] * resolution)
    grid.info.origin.position.y = float(lower[1] * resolution)
    grid.info.origin.orientation.w = 1.0
    grid.data = data.ravel().tolist()
    return grid


def write_bundle(points, grid, output, settings):
    """Commit manifest last. Interrupted/mixed exports fail navigation checks."""
    output = Path(output).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    pcd = output / 'map.pcd'
    pending = output / 'map.pcd.tmp'
    header = ('# .PCD v0.7 - Point-LIO camera_init coordinates\nVERSION 0.7\n'
              'FIELDS x y z\nSIZE 4 4 4\nTYPE F F F\nCOUNT 1 1 1\n'
              f'WIDTH {len(points)}\nHEIGHT 1\nVIEWPOINT 0 0 0 1 0 0 0\n'
              f'POINTS {len(points)}\nDATA binary\n')
    with pending.open('wb') as stream:
        stream.write(header.encode('ascii'))
        stream.write(np.asarray(points, dtype='<f4').tobytes())
    pending.replace(pcd)
    write_grid(grid, output)
    manifest = dict(settings, format='pointlio_pcd_projection_v1',
                    frame='map', source_frame='camera_init', map_to_camera_init=[0, 0, 0, 0, 0, 0],
                    points=len(points), grid_free_space='unoccupied_inside_projection_bounds',
                    sha256={name: hashlib.sha256((output / name).read_bytes()).hexdigest()
                            for name in ('map.pcd', 'map.pgm', 'map.yaml')})
    pending = output / 'map_bundle.json.tmp'
    pending.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    pending.replace(output / 'map_bundle.json')


class PcdMapSaver(Node):
    def __init__(self, args):
        super().__init__('pcd_map_saver', parameter_overrides=[
            rclpy.parameter.Parameter('use_sim_time', value=args.use_sim_time.lower() == 'true')])
        self.args = args
        self.latest = None
        self.voxels = {}
        self.dirty = False
        self.saved = False
        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)
        self.settings = {name: getattr(args, name) for name in
                         ('resolution', 'ground_z', 'min_height', 'max_height', 'voxel_size',
                          'max_range')}
        self.settings.update(range_origin_frame='body', range_metric='horizontal')
        self.subscription = self.create_subscription(
            PointCloud2, args.input_topic, self.receive,
            QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT))
        self.publisher = self.create_publisher(
            OccupancyGrid, '/map', QoSProfile(depth=1,
                durability=DurabilityPolicy.TRANSIENT_LOCAL, reliability=ReliabilityPolicy.RELIABLE))
        # Mapping sidecar samples at 2 Hz; no change to Point-LIO cloud output.
        self.timer = self.create_timer(0.5, self.accumulate)
        self.save_timer = self.create_timer(args.interval, self.save)

    def receive(self, msg):
        if msg.header.frame_id != 'camera_init':
            raise ValueError(f'PCD export requires camera_init; received {msg.header.frame_id!r}')
        self.latest = msg

    def accumulate(self):
        if self.latest is None:
            return
        msg = self.latest
        try:
            # Registered XYZ is in the world frame. Range must follow the IMU
            # at this cloud's stamp, not the power-on origin or the latest pose.
            transform = self.tf_buffer.lookup_transform(
                'camera_init', 'body', rclpy.time.Time.from_msg(msg.header.stamp))
        except tf2_ros.TransformException as error:
            self.get_logger().warning(
                f'Waiting for cloud-time IMU TF before PCD accumulation: {error}',
                throttle_duration_sec=5.0)
            return
        self.latest = None
        points = read_xyz(msg)
        if not len(points):
            return
        if np.max(np.abs(points)) > 10000:
            raise ValueError('Invalid Point-LIO coordinates beyond 10 km')
        origin = transform.transform.translation
        if not all(math.isfinite(value) for value in (origin.x, origin.y)):
            raise ValueError('Invalid IMU position for PCD range filtering')
        distance_squared = ((points[:, 0].astype(np.float64) - origin.x) ** 2 +
                            (points[:, 1].astype(np.float64) - origin.y) ** 2)
        points = points[distance_squared <= self.args.max_range ** 2]
        if not len(points):
            return
        cells = np.floor(points / self.args.voxel_size).astype(np.int64)
        _, selected = np.unique(cells, axis=0, return_index=True)
        for cell, point in zip(cells[selected], points[selected]):
            # Store only XYZ, not a view retaining an entire incoming scan.
            self.voxels.setdefault(tuple(cell), point.copy())
        self.dirty = True

    def save(self):
        self.accumulate()
        if not self.voxels or not self.dirty:
            return self.saved
        points = np.asarray(list(self.voxels.values()), dtype=np.float32)
        try:
            grid = project_grid(points, self.args.resolution, self.args.ground_z,
                                self.args.min_height, self.args.max_height)
            write_bundle(points, grid, self.args.output, self.settings)
        except (OSError, ValueError) as error:
            self.get_logger().error(f'PCD/grid export failed: {error}')
            return False
        if rclpy.ok():
            grid.header.stamp = self.get_clock().now().to_msg()
            self.publisher.publish(grid)
        if not self.saved:
            self.get_logger().info(f'Matching PCD/grid bundle: {self.args.output}. Saved periodically and on Ctrl+C.')
        self.saved, self.dirty = True, False
        return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--input-topic', default='/cloud_registered_full')
    parser.add_argument('--interval', type=float, default=10.0)
    parser.add_argument('--resolution', type=float, default=0.05)
    parser.add_argument('--voxel-size', type=float, default=0.05)
    parser.add_argument('--max-range', type=float, default=10.0,
                        help='Maximum horizontal range from cloud-time IMU position, in meters')
    parser.add_argument('--ground-z', type=float, required=True)
    parser.add_argument('--min-height', type=float, required=True)
    parser.add_argument('--max-height', type=float, required=True)
    parser.add_argument('--use-sim-time', choices=['true', 'false', 'True', 'False'], default='false')
    args = parser.parse_args()
    values = (args.interval, args.resolution, args.voxel_size, args.ground_z,
              args.min_height, args.max_height, args.max_range)
    if not all(math.isfinite(v) for v in values) or min(values[:3]) <= 0 or args.max_range <= 0 or not (
            0 <= args.min_height < args.max_height):
        parser.error('Invalid export intervals, dimensions or height band')
    stopping = False

    def stop(signum, frame):
        nonlocal stopping
        stopping = True

    rclpy.init(args=[], signal_handler_options=SignalHandlerOptions.NO)
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    node = PcdMapSaver(args)
    success = False
    try:
        while rclpy.ok() and not stopping:
            rclpy.spin_once(node, timeout_sec=0.2)
    finally:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        success = node.save()
        if not success:
            node.get_logger().error('No final PCD/grid bundle exported. Check cloud reception and height band.')
        node.destroy_node()
        rclpy.try_shutdown()
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
