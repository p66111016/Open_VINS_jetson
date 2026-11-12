#!/usr/bin/env bash
# Only writes inside this project. No sudo, apt install, pip install, or system writes.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="/usr/bin:/bin:${PATH}"
mkdir -p "$root/deps/downloads" "$root/deps/src" "$root/ros2_ws/src"
fetch() {
    local repo="$1" tag="$2" name="$3" dest="$4"
    if [[ -e "$dest" ]]; then
        [[ -f "$dest/.source.json" ]] || { echo "Unmanaged source directory: $dest" >&2; exit 1; }
        echo "Keeping recorded source: $dest"
        return
    fi
    local archive="$root/deps/downloads/$name-$tag.tar.gz"
    if [[ ! -f "$archive" ]]; then
        curl -fL --retry 2 --connect-timeout 15 --max-time 180 \
            "https://codeload.github.com/$repo/tar.gz/refs/tags/$tag" -o "$archive.part"
        mv "$archive.part" "$archive"
    fi
    /usr/bin/python3 - "$archive" "$dest" "$repo" "$tag" <<'PY'
import hashlib,json,sys,tarfile
from pathlib import Path, PurePosixPath
archive,dest,repo,tag=sys.argv[1:]
dest=Path(dest)
with tarfile.open(archive) as tar:
    members=tar.getmembers()
    roots={PurePosixPath(m.name).parts[0] for m in members}
    if len(roots)!=1:
        raise ValueError('Archive must have one root')
    for member in members:
        path=PurePosixPath(member.name)
        if path.is_absolute() or '..' in path.parts or not (member.isfile() or member.isdir()):
            raise ValueError('Unexpected archive member: '+member.name)
    dest.mkdir(parents=True)
    for member in members:
        parts=PurePosixPath(member.name).parts[1:]
        if not parts:
            continue
        target=dest.joinpath(*parts)
        if member.isdir():
            target.mkdir(parents=True,exist_ok=True)
        else:
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(tar.extractfile(member).read())
            target.chmod(member.mode & 0o777)
(dest/'.source.json').write_text(json.dumps(dict(repo=repo,tag=tag,
    sha256=hashlib.sha256(Path(archive).read_bytes()).hexdigest()),indent=2)+'\n')
PY
}
fetch rpng/open_vins v2.7 open_vins "$root/ros2_ws/src/open_vins"
fetch ros-perception/vision_opencv 3.2.1 vision_opencv "$root/deps/src/vision_opencv"
fetch ceres-solver/ceres-solver 2.1.0 ceres "$root/deps/src/ceres"
# Expose only cv_bridge, not unrelated vision_opencv packages.
if [[ ! -e "$root/ros2_ws/src/cv_bridge" ]]; then
    ln -s ../../deps/src/vision_opencv/cv_bridge "$root/ros2_ws/src/cv_bridge"
fi
# libboost headers already exist; runtime/linker component files are private to this project.
mkdir -p "$root/deps/downloads/boost" "$root/deps/boost"
cd "$root/deps/downloads/boost"
for component in python system filesystem thread date-time chrono atomic serialization; do
    if ! compgen -G "libboost-${component}1.74-dev_*.deb" > /dev/null || ! compgen -G "libboost-${component}1.74.0_*.deb" > /dev/null; then
        apt-get download "libboost-${component}1.74.0=1.74.0-14ubuntu3" "libboost-${component}1.74-dev=1.74.0-14ubuntu3"
    fi
done
for package in ./*.deb; do dpkg-deb -x "$package" "$root/deps/boost"; done
sha256sum ./*.deb > SHA256SUMS
