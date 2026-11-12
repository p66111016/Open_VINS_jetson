#!/usr/bin/python3
"""Recover precise image times by exact label join, never by rounded time or EO pose."""
import argparse
import csv
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path


def join(eo, sidecar, image_dir, output):
    def read(path):
        with Path(path).open(newline='', encoding='utf-8-sig') as f:
            return list(csv.DictReader(f))
    truth, source = read(eo), read(sidecar)
    mapping = {}
    for row in source:
        label = row['Label']
        if label in mapping:
            raise ValueError('Duplicate sidecar label: ' + label)
        value = Decimal(row['unix_utc+8'])
        if not value.is_finite() or value != value.to_integral_value():
            raise ValueError('Invalid precise timestamp: ' + label)
        mapping[label] = int(value)
    selected, missing = [], []
    names, original_times = set(), []
    invalid_times = 0
    for row in truth:
        label = row['Label']
        if label in names or Path(label).name != label:
            raise ValueError('Duplicate or unsafe EO label: ' + label)
        names.add(label)
        try:
            value = Decimal(row['unix_us'])
            if not value.is_finite():
                raise InvalidOperation
            original_times.append(value)
        except InvalidOperation:
            invalid_times += 1
        if label not in mapping:
            missing.append(label)
            continue
        if not (Path(image_dir) / label).is_file():
            raise ValueError('Image missing: ' + label)
        selected.append((label, mapping[label]))
    if len(selected) < 2:
        raise ValueError('Too few exact filename matches')
    if any(b[1] <= a[1] for a, b in zip(selected, selected[1:])):
        raise ValueError('Joined timestamps are not strictly increasing in EO order')
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    report = dict(eo_file=str(eo), precise_timestamp_source=str(sidecar),
                  eo_rows=len(truth), eo_invalid_time_rows=invalid_times,
                  eo_valid_time_unique_count=len(set(original_times)),
                  retained_images=len(selected), excluded_without_precise_timestamp=len(missing),
                  excluded_labels=missing, first_image=selected[0][0], last_image=selected[-1][0],
                  output=str(target), method='Exact Label join; sidecar timestamps copied without interpolation.',
                  eo_pose_used_as_estimator_input=False,
                  sha256={str(p):hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in (eo,sidecar)})
    with target.open('x', newline='') as f:
        w = csv.writer(f)
        w.writerow(['Label','unix_us'])
        w.writerows(selected)
    target.with_suffix('.provenance.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--eo', required=True)
    p.add_argument('--sidecar', required=True)
    p.add_argument('--image-dir', required=True)
    p.add_argument('--output', required=True)
    a = p.parse_args()
    report = join(a.eo,a.sidecar,a.image_dir,a.output)
    print(json.dumps({k:v for k,v in report.items() if k!='excluded_labels'},indent=2))


if __name__=='__main__':
    main()
