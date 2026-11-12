"""Derive rate statistics from measurement stamps and recorded processing times."""
import re
import json


def rate(stamps):
    if len(stamps)<2 or stamps[-1]<=stamps[0]:return None
    return (len(stamps)-1)*1e9/(stamps[-1]-stamps[0])


def measure_fps(root, frames, odometry):
    import numpy as np
    replay=(root/'replay.log').read_text(errors='replace')
    log=(root/'openvins.log').read_text(errors='replace')
    durations=[float(t) for t in re.findall(r'\[TIME\]:\s+([0-9.]+) seconds total',log)]
    durations=[t for t in durations if t>0]
    # These log timestamps measure wall time over the progress-reporting window.
    progress=[(float(t),int(n)) for t,n in re.findall(
        r'\[INFO\]\s+\[([0-9.]+)\].*?Published\s+\{\x27images\x27:\s*(\d+)',replay)]
    observed=None
    if len(progress)>=2 and progress[-1][0]>progress[0][0]:
        observed=(progress[-1][1]-progress[0][1])/(progress[-1][0]-progress[0][0])
    speed_match=re.search(r'"speed":\s*([0-9.eE+-]+)',replay)
    speed=float(speed_match.group(1)) if speed_match else None
    source=rate([int(f['timestamp_ns']) for f in frames])
    measured_replay=None
    for line in replay.splitlines():
        try:
            item=json.loads(line)
            if isinstance(item,dict) and 'replay_timing' in item:measured_replay=item['replay_timing']
        except ValueError:pass
    timing=None
    if durations:
        ms=np.asarray(durations)*1000
        timing=dict(mean=float(ms.mean()),median=float(np.median(ms)),p95=float(np.percentile(ms,95)),max=float(ms.max()))
    return dict(
        source_image_fps=source,
        replay_speed=speed,
        replay_target_image_fps=source*speed if source is not None and speed is not None else None,
        replay_observed_image_fps=observed,
        measured_input_pipeline=measured_replay,
        replay_observation_window_s=progress[-1][0]-progress[0][0] if len(progress)>=2 else None,
        replay_observation_window_images=progress[-1][1]-progress[0][1] if len(progress)>=2 else None,
        openvins_timed_updates=len(durations),
        openvins_processing_fps=len(durations)/sum(durations) if durations else None,
        openvins_timed_updates_per_replay_wall_second=(len(durations)/measured_replay['wall_elapsed_s']
            if measured_replay and measured_replay.get('wall_elapsed_s',0)>0 else None),
        openvins_update_time_ms=timing,
        odometry_output_hz_measurement_time=rate([int(r['timestamp_ns']) for r in odometry]),
        definitions=dict(
            source_image_fps='(image_count - 1) / actual image measurement time span',
            replay_observed_image_fps='Publication count difference / wall-clock span between first and last progress logs; partial run window',
            openvins_processing_fps='Timed camera updates / sum of OpenVINS [TIME] seconds; includes feed_measurement_camera and visualization, excludes image decode, ROS wait and IMU-only work; not end-to-end FPS',
            openvins_timed_updates_per_replay_wall_second='Logged camera update count / full replay loop wall time, including decode, preprocessing, concurrent processing and scheduled waits. Camera frequency policy may skip input images; not a maximum throughput benchmark or per-image completion latency.',
            odometry_output_hz_measurement_time='Odometry count over its measurement-time span; not camera FPS',
            precision='OpenVINS durations are rounded in the source log; rates are estimates from those values'))
