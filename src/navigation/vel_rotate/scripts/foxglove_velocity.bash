#!/usr/bin/env bash
# Read-only velocity plots on the robot host. No build required.
set -eo pipefail
package_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
nav_workspace="$(cd -- "$package_dir/../../.." && pwd)"
source /opt/ros/humble/setup.bash
source "${QD_WORKSPACE:-/home/robomaster/QD_Vision26}/install/setup.bash"
source "$nav_workspace/install/setup.bash"
export ROS_DOMAIN_ID=0 ROS_LOCALHOST_ONLY=0 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export FASTRTPS_DEFAULT_PROFILES_FILE="$package_dir/config/fastdds_udp.xml"
export FASTDDS_DEFAULT_PROFILES_FILE="$FASTRTPS_DEFAULT_PROFILES_FILE"
exec ros2 run foxglove_bridge foxglove_bridge --ros-args \
  -r __node:=foxglove_velocity_bridge \
  --params-file "$package_dir/config/foxglove_velocity.yaml"
