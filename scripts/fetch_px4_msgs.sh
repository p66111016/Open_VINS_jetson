#!/usr/bin/env bash
# Select only after checking the actual firmware release. No system package installation.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
version="${1:-}"
[[ "$version" =~ ^1\.(14|15|16|17)$ ]] || { echo 'Usage: fetch_px4_msgs.sh 1.XX (match actual PX4 firmware release)' >&2; exit 2; }
dest="$root/ros2_ws/src/px4_msgs"
[[ ! -e "$dest" ]] || { echo 'px4_msgs already exists; inspect its version before changing it.' >&2; exit 2; }
archive="$root/deps/downloads/px4_msgs-release-$version.tar.gz"
curl -fL --connect-timeout 15 --max-time 120 "https://codeload.github.com/PX4/px4_msgs/tar.gz/refs/heads/release/$version" -o "$archive"
/usr/bin/python3 - "$archive" "$dest" "$version" <<'PY'
import tarfile,sys,json,hashlib
from pathlib import Path,PurePosixPath
a,d,v=sys.argv[1:];dest=Path(d)
with tarfile.open(a) as tar:
    members=tar.getmembers()
    for m in members:
        p=PurePosixPath(m.name)
        if p.is_absolute() or '..' in p.parts or not(m.isfile() or m.isdir()):raise ValueError('Unsafe member')
    if len({PurePosixPath(m.name).parts[0] for m in members})!=1:raise ValueError('Expected archive root')
    dest.mkdir()
    for m in members:
        parts=PurePosixPath(m.name).parts[1:]
        if not parts:continue
        p=dest.joinpath(*parts)
        if m.isdir():p.mkdir(parents=True,exist_ok=True)
        else:p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(tar.extractfile(m).read())
(dest/'.source.json').write_text(json.dumps(dict(firmware_release=v,archive_sha256=hashlib.sha256(Path(a).read_bytes()).hexdigest()),indent=2)+'\n')
PY
source "$root/scripts/ros_env.sh"
cd "$root/ros2_ws"
colcon build --symlink-install --packages-select px4_msgs --cmake-args -DBUILD_TESTING=OFF
