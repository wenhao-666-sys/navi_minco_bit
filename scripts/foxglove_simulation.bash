#!/usr/bin/env bash
# Simulation observations only; inherit the simulation's DDS environment.
set -eo pipefail
nav_workspace="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
source /opt/ros/humble/setup.bash
source "$nav_workspace/install/setup.bash"
exec ros2 run foxglove_bridge foxglove_bridge --ros-args \
  -r __node:=foxglove_simulation_bridge \
  --params-file "$nav_workspace/src/simulation/sentry_simulation/config/foxglove_navigation.yaml" \
  "$@"
