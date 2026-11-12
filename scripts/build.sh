#!/usr/bin/env bash
set -eo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
source "$root/scripts/ros_env.sh"
jobs="${OPENVINS_BUILD_JOBS:-2}"
mkdir -p "$root/logs" "$root/deps/build"
for path in "$root/deps/src/ceres/CMakeLists.txt" "$root/ros2_ws/src/open_vins/ov_msckf/CMakeLists.txt" "$root/ros2_ws/src/cv_bridge/CMakeLists.txt"; do
    [[ -f "$path" ]] || { echo "Missing source: $path. Run scripts/fetch_sources.sh in a network-enabled terminal." >&2; exit 2; }
done
[[ -e "$root/deps/boost/usr/lib/aarch64-linux-gnu/libboost_python310.so" ]] || { echo 'Missing project-local Boost.Python files; run fetch_sources.sh.' >&2; exit 2; }
/usr/bin/python3 "$root/scripts/apply_source_patches.py"
cmake -S "$root/deps/src/ceres" -B "$root/deps/build/ceres" \
    -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$root/deps/prefix" \
    -DCMAKE_POSITION_INDEPENDENT_CODE=ON -DBUILD_SHARED_LIBS=ON \
    -DBUILD_TESTING=OFF -DBUILD_EXAMPLES=OFF -DBUILD_BENCHMARKS=OFF \
    -DMINIGLOG=ON -DGFLAGS=OFF -DSUITESPARSE=OFF -DCXSPARSE=OFF \
    -DLAPACK=OFF -DCUDA=OFF -DEIGENSPARSE=ON -DSCHUR_SPECIALIZATIONS=OFF \
    -DEXPORT_BUILD_DIR=OFF -DCMAKE_EXPORT_NO_PACKAGE_REGISTRY=ON \
    2>&1 | tee "$root/logs/ceres-configure.log"
cmake --build "$root/deps/build/ceres" --parallel "$jobs" 2>&1 | tee "$root/logs/ceres-build.log"
cmake --install "$root/deps/build/ceres" 2>&1 | tee "$root/logs/ceres-install.log"
export CMAKE_PREFIX_PATH="$root/deps/prefix:${CMAKE_PREFIX_PATH:-}"
export CMAKE_BUILD_PARALLEL_LEVEL="$jobs"
export MAKEFLAGS="-j$jobs -l$jobs"
cd "$root/ros2_ws"
# Build only the estimator chain and this project's tools. ArUco is optional and absent in host OpenCV.
colcon build --symlink-install --executor sequential \
    --packages-up-to cv_bridge ov_msckf mono_openvins_tools \
    --cmake-args -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF \
    -DENABLE_ARUCO_TAGS=OFF -DDISABLE_MATPLOTLIB=ON \
    -DOpenCV_DIR=/usr/lib/cmake/opencv4 \
    -DCeres_DIR="$root/deps/prefix/lib/cmake/Ceres" \
    -DPYTHON_EXECUTABLE=/usr/bin/python3 -DPython3_EXECUTABLE=/usr/bin/python3 \
    -DBoost_NO_BOOST_CMAKE=ON \
    -DBOOST_LIBRARYDIR="$root/deps/boost/usr/lib/aarch64-linux-gnu" \
    -DCMAKE_EXPORT_NO_PACKAGE_REGISTRY=ON \
    2>&1 | tee "$root/logs/colcon-build.log"
"$root/scripts/check_links.sh"
