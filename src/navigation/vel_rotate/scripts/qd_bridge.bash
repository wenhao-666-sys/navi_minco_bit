#!/usr/bin/env bash
# Run with bash. Source-tree launcher: no rebuild required.
set -eo pipefail

package_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
nav_workspace="$(cd -- "$package_dir/../../.." && pwd)"
profile="$package_dir/config/fastdds_udp.xml"
mode="${1:-}"
container="${QD_CONTAINER:-rv_devel_}"
qd_workspace="${QD_WORKSPACE:-/home/robomaster/QD_Vision26}"
# The original vision launch also sets its participants to domain 0.
export ROS_DOMAIN_ID=0
export ROS_LOCALHOST_ONLY=0
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp

case "$mode" in
  serial|vision)
    if docker exec "$container" bash -c '
      pgrep -x rm_serial_drive >/dev/null ||
      pgrep -f "[r]clcpp_components/component_container_mt.*__node:=rm_container" >/dev/null
    '; then
      echo '独立串口或完整视觉容器已经运行，请先在原终端 Ctrl+C，避免重复打开串口。' >&2
      exit 1
    fi
    # Docker only mounts the QD workspace; copy this profile into its /tmp.
    docker exec -i "$container" bash -c 'cat > /tmp/sentry-nav-fastdds-udp.xml' < "$profile"
    docker_args=(exec -i)
    if [[ -t 0 && -t 1 ]]; then docker_args+=(-t); fi
    exec docker "${docker_args[@]}" \
      -e ROS_DOMAIN_ID -e ROS_LOCALHOST_ONLY -e RMW_IMPLEMENTATION \
      -e FASTRTPS_DEFAULT_PROFILES_FILE=/tmp/sentry-nav-fastdds-udp.xml \
      -e FASTDDS_DEFAULT_PROFILES_FILE=/tmp/sentry-nav-fastdds-udp.xml \
      "$container" bash -lc '
        source /opt/ros/humble/setup.bash || exit
        source /ros_ws/install/setup.bash || exit
        # The existing UART driver inherits PARMRK. It duplicates 0xff bytes and
        # corrupts binary frame length/CRC; clear it on the configured port.
        python3 - <<"PY" || exit
import os
import termios
import yaml
with open("/ros_ws/install/rm_bringup/share/rm_bringup/config/node_params/serial_driver_params.yaml") as f:
    port = yaml.safe_load(f)["/**"]["ros__parameters"]["port_name"]
fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
try:
    attrs = termios.tcgetattr(fd)
    attrs[0] &= ~termios.PARMRK
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
finally:
    os.close(fd)
PY
        if [[ "$1" == vision ]]; then
          exec ros2 launch rm_bringup bringup_SingleProcess.launch.py
        fi
        exec ros2 run rm_serial_driver rm_serial_driver_node --ros-args \
          --params-file /ros_ws/install/rm_bringup/share/rm_bringup/config/node_params/serial_driver_params.yaml \
          -p enable_mode_sync:=false
      ' -- "$mode"
    ;;
  rotate|yaw|send)
    source /opt/ros/humble/setup.bash
    source "$qd_workspace/install/setup.bash"
    source "$nav_workspace/install/setup.bash"
    export FASTRTPS_DEFAULT_PROFILES_FILE="$profile"
    export FASTDDS_DEFAULT_PROFILES_FILE="$profile"
    if [[ "$mode" == rotate ]]; then
      if pgrep -f '[v]el_rotate/lib/vel_rotate/vel_rotate_node' >/dev/null; then
        echo 'vel_rotate 已经运行，请先在原终端 Ctrl+C，避免重复发布速度。' >&2
        exit 1
      fi
      exec ros2 run vel_rotate vel_rotate_node --ros-args \
        --params-file "$nav_workspace/src/navigation/navi2_bringup/params/sentry1.yaml"
    elif [[ "$mode" == yaw ]]; then
      exec ros2 topic echo --no-daemon --qos-profile sensor_data \
        /serial/receive rm_interfaces/msg/SerialReceiveData --field big_yaw
    else
      exec ros2 topic echo --no-daemon --qos-profile sensor_data \
        /serial/send rm_interfaces/msg/SerialSendData
    fi
    ;;
  *)
    echo '用法：bash qd_bridge.bash {vision|serial|rotate|yaw|send}（均在主机普通终端执行）' >&2
    exit 2
    ;;
esac
