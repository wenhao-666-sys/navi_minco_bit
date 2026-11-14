#!/usr/bin/env python3
"""主机伪终端集成验证；必须先 source 本工作区，不连接硬件。"""
import errno
import os
from pathlib import Path
import pty
import signal
import struct
import subprocess
import tempfile
import termios
import time

import rclpy
from ament_index_python.packages import get_package_prefix
from geometry_msgs.msg import Twist
from nav_serial_driver.msg import SerialReceiveData, SerialSendData
from rclpy.qos import qos_profile_sensor_data


# 有效浮点数包含连续 0xff，验证载荷的二进制透明性。
BIG_YAW = struct.unpack('<f', bytes.fromhex('fffff742'))[0]

def crc(data):
    value = 0xffff
    for byte in data:
        value ^= byte
        for _ in range(8):
            value = (value >> 1) ^ (0x8408 if value & 1 else 0)
    return value


def feedback():
    data = struct.pack('<2sffff', b'GD', 1.25, -2.5, 0.75, BIG_YAW)
    return data + struct.pack('<H', crc(data))


def main():
    rclpy.init()
    node = rclpy.create_node('nav_serial_pty_test')
    received, sent, actual = [], [], []
    node.create_subscription(SerialReceiveData, '/nav/serial/receive', received.append, qos_profile_sensor_data)
    node.create_subscription(SerialSendData, '/nav/serial/send', sent.append, qos_profile_sensor_data)
    node.create_subscription(Twist, '/cmd_vel_real', actual.append, qos_profile_sensor_data)
    publisher = node.create_publisher(Twist, '/cmd_vel_mpc', qos_profile_sensor_data)
    masters, slaves = [], []
    wire = bytearray()
    frames = []

    def open_pty():
        master, slave = pty.openpty()
        os.set_blocking(master, False)
        # 验证驱动能清除上一个使用者遗留的 PARMRK。
        attrs = termios.tcgetattr(slave)
        attrs[0] |= termios.PARMRK | termios.IXOFF | termios.INLCR
        termios.tcsetattr(slave, termios.TCSANOW, attrs)
        masters.append(master)
        slaves.append(slave)
        return master, os.ttyname(slave)

    master, path = open_pty()

    def pump(seconds):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            rclpy.spin_once(node, timeout_sec=0.01)
            try:
                chunk = os.read(master, 65536)
                wire.extend(chunk)
            except OSError as error:
                if error.errno not in (errno.EIO, errno.EAGAIN):
                    raise
            while len(wire) >= 16:
                if wire[:2] != b'QY':
                    del wire[0]
                    continue
                frame = bytes(wire[:16])
                del wire[:16]
                assert crc(frame[:14]) == struct.unpack('<H', frame[14:])[0]
                frames.append(struct.unpack('<2sfffH', frame))

    def command(x, y, z):
        message = Twist()
        message.linear.x, message.linear.y, message.angular.z = x, y, z
        publisher.publish(message)

    proc = None
    try:
        with tempfile.TemporaryDirectory(prefix='nav-serial-test-') as directory:
            link = Path(directory) / 'uart'
            link.symlink_to(path)
            with open(Path(directory) / 'node.log', 'w+') as log:
                proc = subprocess.Popen([str(Path(get_package_prefix('nav_serial_driver')) / 'lib/nav_serial_driver/nav_serial_node'),
                                         '--ros-args', '-p', f'port_name:={link}'],
                                        stdout=log, stderr=subprocess.STDOUT)
                pump(2)
                assert proc.poll() is None and frames, 'Node startup / zero frame failed'
                assert frames[-1][1:4] == (0., 0., 0.)
                assert not termios.tcgetattr(slaves[-1])[0] & (termios.PARMRK | termios.IXOFF | termios.INLCR)
                for _ in range(5):
                    command(1.25, -2.5, .75)
                    pump(.04)
                assert any(f[1:4] == (1.25, -2.5, .75) for f in frames)
                assert any((m.linear_x, m.linear_y, m.angular_z) == (1.25, -2.5, .75) for m in sent)
                pump(.4)
                assert frames[-1][1:4] == (0., 0., 0.), 'Watchdog did not stop'
                command(float('nan'), 1., 1.)
                pump(.08)
                assert frames[-1][1:4] == (0., 0., 0.)
                command(1e100, 1., 1.)
                pump(.08)
                assert frames[-1][1:4] == (0., 0., 0.)
                valid = feedback()
                bad = valid[:-1] + bytes([valid[-1] ^ 1])
                os.write(master, b'noise\xff' + bad + valid[:8])
                pump(.08)
                assert not received
                os.write(master, valid[8:] + valid)
                pump(.2)
                assert len(received) == 2 and len(actual) == 2
                assert received[-1].big_yaw == BIG_YAW
                assert received[-1].header.stamp.sec > 0
                assert (actual[-1].linear.x, actual[-1].linear.y, actual[-1].angular.z) == (1.25, -2.5, .75)
                # 视觉同名旧话题不得污染导航反馈。
                visual = node.create_publisher(SerialReceiveData, '/serial/receive', qos_profile_sensor_data)
                pump(.2)
                visual.publish(SerialReceiveData(big_yaw=999.))
                pump(.15)
                assert len(received) == 2
                # 拔线后不报告发送成功；换伪终端并重连。
                os.close(master)
                masters.remove(master)
                master, path = open_pty()
                link.unlink()
                pump(.3)
                before = len(sent)
                for _ in range(6):
                    command(2., 3., 4.)
                    pump(.1)
                assert len(sent) == before, 'Failed UART write was published as successful'
                link.symlink_to(path)
                wire.clear()
                frames.clear()
                pump(1.3)
                assert frames and frames[-1][1:4] == (0., 0., 0.)
                command(2., 3., 4.)
                pump(.1)
                assert frames[-1][1:4] == (2., 3., 4.)
                os.write(master, valid)
                pump(.15)
                assert len(received) == 3
                proc.send_signal(signal.SIGINT)
                pump(.3)
                proc.wait(timeout=3)
                assert proc.returncode == 0 and frames[-1][1:4] == (0., 0., 0.)
                print('PASS: startup, direct TX, telemetry, watchdog, invalid values, binary transparency, parser resync, topic isolation, failed write, reconnect, shutdown')
    finally:
        if proc is not None and proc.poll() is None:
            proc.send_signal(signal.SIGINT)
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        for fd in masters + slaves:
            os.close(fd)
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
