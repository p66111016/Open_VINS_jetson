#!/usr/bin/python3
"""Summarize actual odometry output without claiming accuracy from placeholder calibration."""
import argparse
import csv
import json
import math
from pathlib import Path

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('run_directory')
a=p.parse_args()
root=Path(a.run_directory)
rows=[]
if (root/'odometry.csv').exists():
    with (root/'odometry.csv').open() as f:
        rows=list(csv.DictReader(f))
log=(root/'openvins.log').read_text(errors='replace') if (root/'openvins.log').exists() else ''
replay=(root/'replay.log').read_text(errors='replace') if (root/'replay.log').exists() else ''
published=None
for line in replay.splitlines():
    try:
        value=json.loads(line)
    except (ValueError,TypeError):
        continue
    if isinstance(value,dict) and 'published' in value:
        published=value
fields=('px','py','pz','qx','qy','qz','qw','vx_imu','vy_imu','vz_imu')
exit_file=root/'process_exit_codes.txt'
exit_codes=[int(line.split()[1]) for line in exit_file.read_text().splitlines()] if exit_file.exists() else None
result=dict(odometry_messages=len(rows),replay_publications=published,
            process_exit_codes=exit_codes,
            shutdown_clean=(all(code==0 for code in exit_codes) if exit_codes is not None else None),
            fatal_log_lines=[line for line in log.splitlines() if any(k in line.lower() for k in ('assertion','terminate called','segmentation fault'))],
            odometry_all_finite=all(all(math.isfinite(float(r[k])) for k in fields) for r in rows) if rows else None,
            first_odometry_timestamp_ns=int(rows[0]['timestamp_ns']) if rows else None,
            last_odometry_timestamp_ns=int(rows[-1]['timestamp_ns']) if rows else None,
            initialization_log_tail=[s for s in log.splitlines() if any(k in s.lower() for k in ('initialized','initialization','initializ','unable to parse'))][-12:],
            calibration_status=json.loads((root/'calibration_status.json').read_text()),
            mode=json.loads((root/'run_mode.json').read_text()),
            accuracy_verified=False,px4_connected=False)
(root/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
