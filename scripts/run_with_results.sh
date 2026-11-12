#!/usr/bin/env bash
set -eo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
run="$root/results/run_$(date +%Y%m%dT%H%M%S)"
OPENVINS_RUN_DIR="$run" bash "$root/scripts/run_offline.sh" \
    "$root/results/20260622_200hz/normalized_experimental" \
    "$root/config/offline_experimental" "${1:-300}" "${2:-0.5}" --exploratory
source "$root/scripts/ros_env.sh"
/usr/bin/python3 "$root/scripts/summarize_run.py" "$run"
/usr/bin/python3 "$root/scripts/export_results.py" "$run"
/usr/bin/python3 "$root/scripts/validate_media.py" "$run"
echo "Results: $run"
