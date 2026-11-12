#!/usr/bin/env bash
# Source in a dedicated terminal. Never add to .bashrc or source cuVSLAM first.
openvins_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IFS=: read -r -a openvins_prefixes <<< "${AMENT_PREFIX_PATH:-}"
for openvins_prefix in "${openvins_prefixes[@]}"; do
    case "$openvins_prefix" in
        ''|/opt/ros/humble|"${openvins_root}/ros2_ws/install"/*) ;;
        *) echo 'Use a fresh terminal: another ROS workspace is already sourced.' >&2
           unset openvins_root openvins_prefixes openvins_prefix
           return 1 ;;
    esac
done
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:${PATH}"
unset PYTHONHOME
export PYTHONNOUSERSITE=1
# Discard inherited Python/ROS search paths in this terminal only.
unset PYTHONPATH AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH
export LD_LIBRARY_PATH="${openvins_root}/deps/prefix/lib:${openvins_root}/deps/boost/usr/lib/aarch64-linux-gnu:/opt/ros/humble/lib"
source /opt/ros/humble/setup.bash
if [[ -f "${openvins_root}/ros2_ws/install/local_setup.bash" ]]; then
    source "${openvins_root}/ros2_ws/install/local_setup.bash"
fi
if [[ -d "${openvins_root}/deps/prefix" ]]; then
    export CMAKE_PREFIX_PATH="${openvins_root}/deps/prefix:${CMAKE_PREFIX_PATH:-}"
fi
export ROS_DOMAIN_ID="${OPENVINS_ROS_DOMAIN_ID:-91}"
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export ROS_LOCALHOST_ONLY=1
export ROS_LOG_DIR="${openvins_root}/logs/ros"
unset openvins_root openvins_prefixes openvins_prefix
