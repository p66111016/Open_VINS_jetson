"""Read-only audit and explicit normalization of historical sensor records.

No attitude, GPS, EO position, or interpolated per-image IMU is used as VIO input.
The unix_utc+8 column is treated as an integer label; no timezone shift is guessed.
"""
import argparse
import csv
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import statistics


def integer(value):
    parsed = Decimal(str(value))
    if not parsed.is_finite() or parsed != parsed.to_integral_value():
        raise ValueError(f'Expected exact integer timestamp, got {value!r}')
    return int(parsed)


def read_csv(path):
    with Path(path).open(newline='', encoding='utf-8-sig') as stream:
        return list(csv.DictReader(stream))


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def window_imu(config, image_times, imu):
    preroll = float(config.get('imu_preroll_s', 2.0))
    postroll = float(config.get('imu_postroll_s', 0.1))
    if not math.isfinite(preroll) or not math.isfinite(postroll) or preroll < 0 or postroll <= 0:
        raise ValueError('Invalid IMU pre/postroll')
    lo, hi = image_times[0] - round(preroll * 1e6), image_times[-1] + round(postroll * 1e6)
    return [row for row in imu if lo <= integer(row['unix_us']) <= hi]


def time_stats(values):
    if len(values) < 2:
        raise ValueError('At least two samples required')
    delta = [b - a for a, b in zip(values, values[1:])]
    positive = [d for d in delta if d > 0]
    return dict(count=len(values), first_us=values[0], last_us=values[-1],
                nonpositive_deltas=sum(d <= 0 for d in delta),
                median_positive_delta_us=statistics.median(positive) if positive else None,
                min_delta_us=min(delta), max_delta_us=max(delta),
                duration_s=(values[-1] - values[0]) / 1e6)


def load_source(config):
    frames = read_csv(config['image_timestamps_csv'])
    imu = [r for r in read_csv(config['imu_csv'])
           if Decimal(r['I']) == Decimal(str(config['imu_instance']))]
    if not frames or not imu:
        raise ValueError('Empty image or selected IMU stream')
    names = [r['Label'] for r in frames]
    if len(set(names)) != len(names):
        raise ValueError('Duplicate image labels')
    for name in names:
        if Path(name).name != name or name in ('.', '..'):
            raise ValueError(f'Unsafe image label: {name}')
    return frames, imu


def audit(config):
    frames, imu = load_source(config)
    image_t = [integer(r[config['image_time_column']]) for r in frames]
    unix_t = [integer(r['unix_us']) for r in imu]
    boot_t = [integer(r['TimeUS']) for r in imu]
    offsets = [u - b for u, b in zip(unix_t, boot_t)]
    gaps = [dict(row=i + 2, before_unix_us=unix_t[i], after_unix_us=unix_t[i + 1],
                 gap_us=b - a, overlaps_image_window=(unix_t[i] <= image_t[-1] and unix_t[i + 1] >= image_t[0]))
            for i, (a, b) in enumerate(zip(boot_t, boot_t[1:])) if b - a > 50_000]
    active_offsets = [o for o, t in zip(offsets, unix_t) if image_t[0] <= t <= image_t[-1]]
    missing = [r['Label'] for r in frames if not (Path(config['image_dir']) / r['Label']).is_file()]
    nonfinite = sum(not all(math.isfinite(float(r[c])) for c in
                          ('GyrX', 'GyrY', 'GyrZ', 'AccX', 'AccY', 'AccZ')) for r in imu)
    image_stats = time_stats(image_t)
    unix_stats = time_stats(unix_t)
    selected_imu = window_imu(config, image_t, imu)
    selected_t = [integer(r['unix_us']) for r in selected_imu]
    if len(selected_t) < 2:
        raise ValueError('Too few IMU samples in image time window')
    selected_stats = time_stats(selected_t)
    issues = []
    if not config.get('dataset_confirmed', False):
        issues.append('Candidate dataset identity has not been confirmed.')
    if image_stats['nonpositive_deltas']:
        issues.append('Image timestamps are not strictly increasing.')
    if selected_stats['nonpositive_deltas']:
        issues.append('Selected IMU unix_us is not strictly increasing; raw replay is blocked.')
    if missing:
        issues.append('Image files are missing.')
    if nonfinite:
        issues.append('IMU contains nonfinite values.')
    if any(g['overlaps_image_window'] for g in gaps):
        issues.append('IMU gap over 50 ms overlaps image window; split or repair the source recording.')
    if not config.get('timebase_reviewed', False):
        issues.append('Camera/IMU clock relationship has not been verified.')
    if not config.get('imu_units_axes_reviewed', False):
        issues.append('IMU units and axes have not been verified.')
    return dict(
        image_dir=config['image_dir'],
        image_timestamp_file=config['image_timestamps_csv'], imu_file=config['imu_csv'],
        image_timestamps=image_stats, imu_unix=unix_stats, imu_boot=time_stats(boot_t),
        selected_imu_unix=selected_stats,
        missing_images=missing[:20], missing_image_count=len(missing), nonfinite_imu=nonfinite,
        imu_unix_minus_boot_us=dict(min=min(offsets), median=statistics.median(offsets),
                                    max=max(offsets), span=max(offsets) - min(offsets)),
        active_window_offset_span_us=max(active_offsets) - min(active_offsets) if active_offsets else None,
        imu_gaps_over_50ms=gaps,
        image_range_inside_imu_unix=(selected_t[0] <= image_t[0] and image_t[-1] < selected_t[-1]),
        input_sha256={k: sha256(config[k]) for k in ('image_timestamps_csv', 'imu_csv')},
        blockers=issues,
        note='No timestamps repaired, samples dropped, units changed, or calibration inferred.')


def prepare(config, output, exploratory=False):
    """Normalize reviewed inputs. Refuse implicit clock repair or unit conversion."""
    report = audit(config)
    review_issues = {'Camera/IMU clock relationship has not been verified.',
                     'IMU units and axes have not been verified.'}
    blockers = [b for b in report['blockers'] if not (exploratory and b in review_issues)]
    if blockers:
        raise ValueError('; '.join(blockers))
    frames, imu = load_source(config)
    times = [integer(r[config['image_time_column']]) for r in frames]
    imu = window_imu(config, times, imu)
    imu_t = [integer(r['unix_us']) for r in imu]
    if not report['image_range_inside_imu_unix']:
        raise ValueError('IMU does not cover all image times')
    # Retain actual measurement intervals; translate both clocks by the same origin.
    origin_us = min(times[0], imu_t[0])
    out = Path(output)
    if out.exists():
        raise ValueError(f'Refusing to overwrite dataset directory: {out}')
    out.mkdir(parents=True)
    with (out / 'frames.csv').open('w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['timestamp_ns', 'path'])
        for row, t in zip(frames, times):
            writer.writerow([(t - origin_us) * 1000 + 1_000_000_000,
                             str((Path(config['image_dir']) / row['Label']).resolve())])
    with (out / 'imu.csv').open('w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['timestamp_ns', 'wx', 'wy', 'wz', 'ax', 'ay', 'az'])
        for row, t in zip(imu, imu_t):
            writer.writerow([(t - origin_us) * 1000 + 1_000_000_000] +
                             [float(row[c]) for c in ('GyrX', 'GyrY', 'GyrZ', 'AccX', 'AccY', 'AccZ')])
    manifest = dict(schema_version=1, source_origin_us=origin_us, replay_origin_ns=1_000_000_000,
                    mode='historical', reviewed=not bool(report['blockers']),
                    exploratory=exploratory, source_config=config, audit=report)
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def load_normalized(directory, start=0, max_frames=0, preroll_s=2.0, exploratory=False):
    directory = Path(directory)
    manifest = json.loads((directory / 'manifest.json').read_text())
    if manifest.get('schema_version') != 1 or manifest.get('mode') != 'historical':
        raise ValueError('Expected historical dataset schema_version=1')
    if not manifest.get('reviewed') and not exploratory:
        raise ValueError('Normalized dataset is not reviewed')
    if start < 0 or max_frames < 0 or not math.isfinite(preroll_s) or preroll_s < 0:
        raise ValueError('Invalid frame selection or preroll')
    all_frames = [(integer(r['timestamp_ns']), r['path']) for r in read_csv(directory / 'frames.csv')]
    imu = [(integer(r['timestamp_ns']), tuple(float(r[c]) for c in ('wx','wy','wz','ax','ay','az')))
           for r in read_csv(directory / 'imu.csv')]
    if not all_frames or not imu:
        raise ValueError('Empty normalized stream')
    for stream in (all_frames, imu):
        if stream[0][0] <= 0 or any(b[0] <= a[0] for a, b in zip(stream, stream[1:])):
            raise ValueError('Normalized timestamps must be positive and strictly increasing')
    if any(not all(math.isfinite(v) for v in values) for _, values in imu):
        raise ValueError('Nonfinite normalized IMU')
    frames = all_frames[start:start + max_frames if max_frames else None]
    if not frames or imu[0][0] > frames[0][0] or imu[-1][0] <= frames[-1][0]:
        raise ValueError('No selected images, or IMU does not bracket selected images')
    if any(not Path(p).is_file() for _, p in frames):
        raise ValueError('Missing normalized image path')
    lo = frames[0][0] - round(preroll_s * 1e9)
    # Include one IMU sample after the last image so OpenVINS can process its final update.
    after = next(i for i, (t, _) in enumerate(imu) if t > frames[-1][0])
    imu = [r for r in imu[:after + 1] if r[0] >= lo]
    return manifest, frames, imu


def events(frames, imu):
    """Merge without float timestamps; IMU precedes image at equal time."""
    import heapq
    yield from heapq.merge(((t, 1, p) for t, p in frames), ((t, 0, v) for t, v in imu))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['audit', 'prepare'])
    parser.add_argument('--config', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--exploratory', action='store_true', help='Allow unreviewed timing/units for offline experiments; keep metadata unreviewed')
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text())
    try:
        if args.action == 'audit':
            report = audit(config)
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            Path(args.output).write_text(json.dumps(report, indent=2) + '\n')
            print(json.dumps(report, indent=2))
        else:
            result = prepare(config, args.output, exploratory=args.exploratory)
            print('Prepared historical dataset:', args.output, result['source_origin_us'])
    except (ValueError, KeyError, FileNotFoundError) as exc:
        parser.exit(2, f'{exc}\n')


if __name__ == '__main__':
    main()
