#!/usr/bin/env bash
set -eo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
source "$root/scripts/ros_env.sh"
/usr/bin/python3 - "$root" <<'PY'
from pathlib import Path
import json,subprocess,sys
root=Path(sys.argv[1])
targets=[root/'ros2_ws/install/ov_msckf/lib/ov_msckf/run_subscribe_msckf',
         root/'ros2_ws/install/cv_bridge/lib/libcv_bridge.so']
result={}
for path in targets:
    if not path.exists():
        raise SystemExit('Not built: '+str(path))
    links=subprocess.check_output(['ldd',str(path)],text=True)
    result[str(path)]=links
    if 'not found' in links:
        raise SystemExit('Unresolved libraries: '+links)
    opencv=[line for line in links.splitlines() if 'libopencv_' in line]
    if not opencv or any('.so.408' not in line.split('=>')[0] for line in opencv):
        raise SystemExit('Expected only OpenCV 4.8 libraries: '+links)
    cv_lines=[line for line in links.splitlines() if 'libcv_bridge.so' in line]
    if path==targets[0] and (not cv_lines or not all(str(root) in line for line in cv_lines)):
        raise SystemExit('Estimator did not load project-local cv_bridge: '+links)
    if path==targets[0]:
        ceres_lines=[line for line in links.splitlines() if 'libceres.so' in line]
        if not ceres_lines or not all(str(root/'deps/prefix') in line for line in ceres_lines):
            raise SystemExit('Estimator did not load project-local Ceres: '+links)
(root/'results/linkage.json').write_text(json.dumps(result,indent=2)+'\n')
print('OpenVINS and cv_bridge resolve to OpenCV 4.8; project-local cv_bridge/Ceres verified.')
PY
