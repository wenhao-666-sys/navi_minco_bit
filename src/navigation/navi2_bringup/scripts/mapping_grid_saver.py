"""Cache OccupancyGrid; export PGM/YAML periodically and on SIGINT/SIGTERM.

No service call is needed during shutdown: the latest received grid is saved
even if slam_toolbox has already stopped. SIGKILL / power loss cannot be caught.
"""
import argparse
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


def write_grid(grid, directory):
    width, height = grid.info.width, grid.info.height
    resolution = float(grid.info.resolution)
    data = np.asarray(grid.data, dtype=np.int16)
    if width <= 0 or height <= 0 or data.size != width * height:
        raise ValueError('Invalid OccupancyGrid dimensions; no map exported.')
    if not math.isfinite(resolution) or resolution <= 0 or np.any((data < -1) | (data > 100)):
        raise ValueError('Invalid OccupancyGrid resolution or occupancy values.')
    p, q = grid.info.origin.position, grid.info.origin.orientation
    yaw = math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))
    if not all(math.isfinite(v) for v in (p.x,p.y,yaw)):
        raise ValueError('Invalid map origin.')
    # ROS stores rows bottom-up. PGM rows are top-down. Unknown remains gray.
    # Gray must remain between the YAML thresholds on reload. 205 would have
    # occupancy ~0.196 and be reloaded as FREE with free_thresh=0.25.
    pixels = np.full(data.shape, 128, dtype=np.uint8)
    pixels[(data >= 0) & (data <= 25)] = 254
    pixels[data >= 65] = 0
    image = np.flipud(pixels.reshape(height,width)).tobytes()
    directory = Path(directory).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    pgm = directory / 'map.pgm'
    metadata = directory / 'map.yaml'
    pgm_tmp = directory / 'map.pgm.tmp'
    yaml_tmp = directory / 'map.yaml.tmp'
    pgm_tmp.write_bytes(f'P5\n{width} {height}\n255\n'.encode('ascii') + image)
    yaml_tmp.write_text(
        'image: ' + json.dumps(pgm.name) + '\n'
        'mode: trinary\n'
        f'resolution: {resolution:.12g}\n'
        f'origin: [{p.x:.12g}, {p.y:.12g}, {yaw:.12g}]\n'
        'negate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.25\n')
    pgm_tmp.replace(pgm)
    yaml_tmp.replace(metadata)
    return metadata


class GridSaver(Node):
    def __init__(self, output, interval):
        super().__init__('mapping_grid_saver')
        self.output = output
        self.latest = None
        self.saved_once = False
        self.subscription = self.create_subscription(
            OccupancyGrid, '/map', self.receive,
            QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                       durability=DurabilityPolicy.TRANSIENT_LOCAL))
        self.timer = self.create_timer(interval, self.save)

    def receive(self, msg):
        if msg.info.width and msg.info.height:
            self.latest = msg
            if not self.saved_once:
                self.save()

    def save(self):
        if self.latest is None:
            return False
        try:
            path = write_grid(self.latest, self.output)
        except (OSError, ValueError) as error:
            self.get_logger().error(f'Map export failed: {error}')
            return False
        if not self.saved_once:
            self.get_logger().info(f'Map received; saving every checkpoint and on shutdown to {path}')
        self.saved_once = True
        return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--interval', type=float, default=10.0)
    args = parser.parse_args()
    if not math.isfinite(args.interval) or args.interval <= 0:
        parser.error('--interval must be positive and finite')
    stopping = False

    def stop(signum, frame):
        nonlocal stopping
        stopping = True

    rclpy.init(args=[], signal_handler_options=SignalHandlerOptions.NO)
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    node = GridSaver(args.output, args.interval)
    success = False
    try:
        while rclpy.ok() and not stopping:
            rclpy.spin_once(node, timeout_sec=0.2)
    finally:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        success = node.save()
        if not success:
            node.get_logger().error('No final map exported. Check /map reception and output permissions; no blank map is generated.')
        node.destroy_node()
        rclpy.shutdown()
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
