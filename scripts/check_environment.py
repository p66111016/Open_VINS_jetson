#!/usr/bin/python3
"""Compare protected host/reference files with the pre-deployment baseline."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
before = json.loads((root / 'results/environment_before.json').read_text())
changes = []
for name, expected in before['files'].items():
    p = Path(name)
    actual = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
    if actual != expected:
        changes.append(name)
dpkg = subprocess.check_output(['dpkg-query','-W','-f=${binary:Package}\t${Version}\n'], text=True)
result = dict(changed_protected_files=changes, dpkg_versions_unchanged=dpkg == before['dpkg'])
(root / 'results/environment_comparison.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
sys.exit(bool(changes or dpkg != before['dpkg']))
