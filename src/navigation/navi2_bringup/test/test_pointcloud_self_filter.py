"""Binary point records and timestamp behavior of the body filter (no ROS nodes)."""
import importlib.util
from pathlib import Path
import struct
import time
from collections import deque
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from geometry_msgs.msg import TransformStamped
from sensor_msgs.msg import PointCloud2, PointField
from std_msgs.msg import Header
from builtin_interfaces.msg import Time
import tf2_ros


spec = importlib.util.spec_from_file_location(
    'pointcloud_self_filter', Path(__file__).parents[1] / 'scripts/pointcloud_self_filter.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
Filter = module.PointCloudSelfFilter


class BodyFilterTest(unittest.TestCase):
    def make_filter(self, translation=0.0):
        transform = TransformStamped()
        transform.header.frame_id = 'body'
        transform.child_frame_id = 'camera_init'
        transform.header.stamp = Time(sec=7)
        transform.transform.rotation.w = 1.0
        transform.transform.translation.x = translation
        buffer = tf2_ros.Buffer()
        buffer.set_transform(transform, 'test')
        node = SimpleNamespace(
            body_frame='body', timeout=0.0, tf_buffer=buffer,
            bounds=(-0.45, 0.45, -0.45, 0.45, -0.30, 1.20),
            _matrix=Filter._matrix, _xyz_array=Filter._xyz_array,
            publisher=Mock(), get_logger=Mock(return_value=Mock()), warned=False,
            pending_clouds=deque(maxlen=3))
        node._process_pending = lambda: Filter._process_pending(node)
        node._filter_cloud = lambda message, transform: Filter._filter_cloud(node, message, transform)
        return node

    def make_cloud(self, bigendian=False):
        fields = [PointField(name=name, offset=offset, datatype=datatype, count=1)
                  for name, offset, datatype in [
                      ('x', 0, PointField.FLOAT32), ('y', 4, PointField.FLOAT32),
                      ('z', 8, PointField.FLOAT32), ('intensity', 12, PointField.FLOAT32),
                      ('ring', 16, PointField.UINT16), ('tag', 18, PointField.UINT8)]]
        points = [(0., 0., 0.), (2., 0., 0.), (float('nan'), 0., 0.), (0., 2., .4)]
        records = [struct.pack(('>' if bigendian else '<') + 'ffffHB5s',
                               *xyz, 10. + i, 100 + i, i, bytes([i + 200]) * 5)
                   for i, xyz in enumerate(points)]
        cloud = PointCloud2(
            header=Header(stamp=Time(sec=7), frame_id='camera_init'),
            height=2, width=2, fields=fields, is_bigendian=bigendian,
            point_step=24, row_step=55,
            data=records[0] + records[1] + b'rowpad!' + records[2] + records[3] + b'rowpad!',
            is_dense=False)
        return cloud, records

    def test_preserves_records_fields_header_and_endianness(self):
        for bigendian in (False, True):
            with self.subTest(bigendian=bigendian):
                node = self.make_filter()
                cloud, records = self.make_cloud(bigendian)
                Filter.callback(node, cloud)
                node.publisher.publish.assert_called_once()
                output = node.publisher.publish.call_args.args[0]
                self.assertEqual(bytes(output.data), records[1] + records[3])
                self.assertEqual(output.fields, cloud.fields)
                self.assertEqual(output.header, cloud.header)
                self.assertEqual(output.is_bigendian, bigendian)
                self.assertEqual((output.height, output.width, output.point_step, output.row_step),
                                 (1, 2, 24, 48))

    def test_crops_in_body_frame_but_keeps_world_coordinates(self):
        node = self.make_filter(translation=-2.0)
        cloud, records = self.make_cloud()
        Filter.callback(node, cloud)
        output = node.publisher.publish.call_args.args[0]
        self.assertEqual(bytes(output.data), records[0] + records[3])

    def test_requires_transform_at_cloud_timestamp(self):
        node = self.make_filter()
        cloud, _ = self.make_cloud()
        cloud.header.stamp = Time(sec=7, nanosec=10_000_000)
        # A pose only 10 ms old must not silently replace the requested pose.
        Filter.callback(node, cloud)
        node.publisher.publish.assert_not_called()
        node.get_logger().warning.assert_called_once()

    def test_empty_filtered_cloud_has_consistent_layout(self):
        node = self.make_filter()
        cloud, records = self.make_cloud()
        cloud.height = 1
        cloud.width = 1
        cloud.row_step = 24
        cloud.data = records[0]
        Filter.callback(node, cloud)
        output = node.publisher.publish.call_args.args[0]
        self.assertEqual((output.height, output.width, output.row_step, len(output.data)),
                         (1, 0, 0, 0))
        self.assertEqual(output.fields, cloud.fields)

    def test_truncated_input_is_rejected(self):
        node = self.make_filter()
        cloud, _ = self.make_cloud()
        cloud.data = bytes(cloud.data[:-1])
        Filter.callback(node, cloud)
        node.publisher.publish.assert_not_called()
        node.get_logger().warning.assert_called_once()

    def test_waits_without_blocking_then_uses_matching_tf(self):
        node = self.make_filter()
        node.timeout = 1.0
        cloud, records = self.make_cloud()
        cloud.header.stamp = Time(sec=7, nanosec=10_000_000)
        Filter.callback(node, cloud)
        node.publisher.publish.assert_not_called()
        self.assertEqual(len(node.pending_clouds), 1)
        transform = TransformStamped()
        transform.header.frame_id = 'body'
        transform.child_frame_id = 'camera_init'
        transform.header.stamp = Time(sec=7, nanosec=20_000_000)
        transform.transform.rotation.w = 1.0
        node.tf_buffer.set_transform(transform, 'test')
        node._process_pending()
        self.assertFalse(node.pending_clouds)
        self.assertEqual(bytes(node.publisher.publish.call_args.args[0].data),
                         records[1] + records[3])

    def test_queue_drops_oldest_and_preserves_output_order(self):
        node = self.make_filter()
        node.timeout = 1.0
        for sec in range(8, 12):
            cloud, _ = self.make_cloud()
            cloud.header.stamp = Time(sec=sec)
            Filter.callback(node, cloud)
        self.assertEqual(len(node.pending_clouds), 3)
        node.publisher.publish.assert_not_called()
        transform = TransformStamped()
        transform.header.frame_id = 'body'
        transform.child_frame_id = 'camera_init'
        transform.header.stamp = Time(sec=12)
        transform.transform.rotation.w = 1.0
        node.tf_buffer.set_transform(transform, 'test')
        node._process_pending()
        self.assertEqual([c.args[0].header.stamp.sec for c in node.publisher.publish.call_args_list],
                         [9, 10, 11])

    def test_expired_wait_drops_frame_and_valid_frame_recovers(self):
        node = self.make_filter()
        node.timeout = 0.05
        cloud, _ = self.make_cloud()
        cloud.header.stamp = Time(sec=8)
        node.pending_clouds.append((cloud, time.monotonic() - 1.0))
        node._process_pending()
        self.assertFalse(node.pending_clouds)
        node.publisher.publish.assert_not_called()
        # A pose becoming available later must not revive an expired frame.
        cloud, _ = self.make_cloud()
        node.pending_clouds.append((cloud, time.monotonic() - 1.0))
        node._process_pending()
        node.publisher.publish.assert_not_called()
        cloud, _ = self.make_cloud()
        Filter.callback(node, cloud)
        node.publisher.publish.assert_called_once()


if __name__ == '__main__':
    unittest.main()
