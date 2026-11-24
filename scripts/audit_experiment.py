"""Audit both fresh room runs and record their input and algorithm provenance."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tests'))
from check_native_support import audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scans', type=Path)
    parser.add_argument('run', type=Path)
    args = parser.parse_args()
    records = {name: audit(str(args.scans/f'{name}.pcd'), args.run/name) for name in ('M04', 'M26')}
    records['git_commit'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    (args.run/'audit.json').write_text(json.dumps(records, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
