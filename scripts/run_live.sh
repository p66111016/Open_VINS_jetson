#!/usr/bin/env bash
# Future driver entry point. Drivers are external and publish the sensor_interface.yaml topics.
set -eo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
if [[ $# != 1 ]]; then echo "Usage: $0 VERIFIED_CALIBRATION_DIR" >&2; exit 2; fi
calibration="$(realpath "$1")"
source "$root/scripts/ros_env.sh"
/usr/bin/python3 - "$calibration/status.json" <<'PY'
import json,sys
s=json.load(open(sys.argv[1]))
for k in ('ready','intrinsics_reviewed','camera_imu_extrinsics_reviewed','camera_imu_time_offset_reviewed','imu_noise_reviewed'):
    if s.get(k) is not True:
        raise SystemExit('Live profile needs actual calibration: '+k)
PY
"$root/scripts/check_links.sh"
exec ros2 run ov_msckf run_subscribe_msckf --ros-args \
    -r __ns:=/openvins -p config_path:="$calibration/estimator_config.yaml" \
    -p max_cameras:=1 -p use_stereo:=false -p use_sim_time:=false \
    -p publish_global_to_imu_tf:=false -p publish_calibration_tf:=false
