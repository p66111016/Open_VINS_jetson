#!/usr/bin/env bash
set -eo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
source "$root/scripts/ros_env.sh"
cd "$root/ros2_ws"
colcon build --symlink-install --executor sequential --packages-select mono_openvins_tools
