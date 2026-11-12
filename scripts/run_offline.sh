#!/usr/bin/env bash
# Native historical OpenVINS runner; no PX4 publisher or Agent is started.
set -eo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
if [[ $# -lt 2 ]]; then
    echo "Usage: $0 NORMALIZED_DATASET CALIBRATION_DIR [MAX_FRAMES=300] [SPEED=0.25] [--exploratory]" >&2
    exit 2
fi
dataset="$(realpath "$1")"
calibration="$(realpath "$2")"
frames="${3:-300}"
speed="${4:-0.25}"
exploratory="${5:-}"
extra=()
if [[ -n "$exploratory" ]]; then
    [[ "$exploratory" == --exploratory ]] || { echo 'Unknown fifth argument' >&2; exit 2; }
    extra+=(--exploratory)
fi
source "$root/scripts/ros_env.sh"
"$root/scripts/check_links.sh"
/usr/bin/python3 - "$calibration" "$exploratory" <<'PY'
import json,sys
from pathlib import Path
import yaml
p=Path(sys.argv[1])
status=json.loads((p/'status.json').read_text())
for key in ('ready','intrinsics_reviewed','camera_imu_extrinsics_reviewed',
            'camera_imu_time_offset_reviewed','imu_noise_reviewed'):
    if status.get(key) is not True and sys.argv[2] != '--exploratory':
        raise SystemExit('Calibration not ready: '+key)
def read(name):
    text=(p/name).read_text()
    if text.startswith('%YAML:1.0'):
        text='\n'.join(text.splitlines()[1:])
    return yaml.safe_load(text)
est=read('estimator_config.yaml')
if est.get('max_cameras') != 1 or est.get('use_stereo') is not False:
    raise SystemExit('Expected max_cameras: 1 and use_stereo: false')
for k,name in (('relative_config_imu','kalibr_imu_chain.yaml'),
               ('relative_config_imucam','kalibr_imucam_chain.yaml')):
    if est.get(k) != name:
        raise SystemExit('Expected '+k+': '+name)
cam=read('kalibr_imucam_chain.yaml')['cam0']
imu=read('kalibr_imu_chain.yaml')['imu0']
if cam['rostopic'] != '/openvins/input/image_raw' or imu['rostopic'] != '/openvins/input/imu':
    raise SystemExit('Calibration topics must use /openvins/input/image_raw and /openvins/input/imu')
if status.get('rectification_applied') is not True:
    raise SystemExit('This runner expects rectified images; raw camera model needs separate review.')
if cam.get('camera_model') != 'pinhole' or cam.get('distortion_model') != 'radtan' or any(cam['distortion_coeffs']):
    raise SystemExit('Rectified input requires pinhole/radtan and zero distortion_coeffs')
raw=Path(status['rectification_ros_yaml'])
if not raw.is_absolute() or not raw.is_file():
    raise SystemExit('rectification_ros_yaml must be an existing absolute path')
info=yaml.safe_load(raw.read_text())
k=info['camera_matrix']['data']
if cam['resolution'] != [info['image_width'],info['image_height']] or any(abs(a-b)>1e-6 for a,b in zip(cam['intrinsics'],[k[0],k[4],k[2],k[5]])):
    raise SystemExit('Rectified OpenVINS intrinsics/resolution differ from replay rectification')
PY
rectification="$(/usr/bin/python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["rectification_ros_yaml"])' "$calibration/status.json")"
run="${OPENVINS_RUN_DIR:-$root/results/run_$(date +%Y%m%dT%H%M%S)}"
mkdir "$run"
cp "$calibration/status.json" "$run/calibration_status.json"
cp "$dataset/manifest.json" "$run/dataset_manifest.json"
/usr/bin/python3 -c 'import json,sys; print(json.dumps({"mode":"historical", "exploratory":bool(sys.argv[1]), "px4_output":False}))' "$exploratory" > "$run/run_mode.json"
pids=()
cleanup() {
    status=$?
    for pid in "${pids[@]}"; do kill -INT "$pid" 2>/dev/null || true; done
    for attempt in {1..15}; do
        running=false
        for pid in "${pids[@]}"; do if kill -0 "$pid" 2>/dev/null; then running=true; fi; done
        if ! $running; then break; fi
        sleep 0.2
    done
    for pid in "${pids[@]}"; do kill -TERM "$pid" 2>/dev/null || true; done
    for pid in "${pids[@]}"; do
        if wait "$pid" 2>/dev/null; then code=0; else code=$?; fi
        echo "$pid $code" >> "$run/process_exit_codes.txt"
        case "$code" in 0|130|143) ;; *) status=1 ;; esac
    done
    exit "$status"
}
trap cleanup EXIT
"$root/ros2_ws/install/ov_msckf/lib/ov_msckf/run_subscribe_msckf" --ros-args \
    -r __ns:=/openvins -p config_path:="$calibration/estimator_config.yaml" \
    -p max_cameras:=1 -p use_stereo:=false -p use_sim_time:=true \
    -p publish_global_to_imu_tf:=false -p publish_calibration_tf:=false \
    > "$run/openvins.log" 2>&1 &
pids+=("$!")
"$root/ros2_ws/install/mono_openvins_tools/lib/mono_openvins_tools/record_odometry" --output "$run/odometry.csv" \
    --ros-args -p use_sim_time:=true > "$run/recorder.log" 2>&1 &
pids+=("$!")
ros2 run mono_openvins_tools replay --dataset "$dataset" --max-frames "$frames" \
    --speed "$speed" --rectify-calibration "$rectification" "${extra[@]}" \
    2>&1 | tee "$run/replay.log"
echo "Historical run saved in $run; inspect initialization and estimator receipt separately."
