#!/usr/bin/env bash
set -eo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$root/ros2_ws/src/mono_openvins_tools"
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
/usr/bin/python3 -m unittest discover -s "$root/tests" -v
for script in "$root"/scripts/*.sh; do bash -n "$script"; done
/usr/bin/python3 "$root/scripts/check_environment.py"
