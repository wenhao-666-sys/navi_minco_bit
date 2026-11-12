#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/humble/setup.bash
# 调用前请 source 当前导航工作区 install/setup.bash。
config="$(ros2 pkg prefix nav_serial_driver)/share/nav_serial_driver/config/foxglove_velocity.yaml"
exec ros2 run foxglove_bridge foxglove_bridge --ros-args -r __node:=foxglove_velocity_bridge --params-file "$config"
