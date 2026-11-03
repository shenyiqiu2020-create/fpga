"""Verify a nonempty, relative-path SHA256 manifest without modifying inputs."""
import argparse
import hashlib
import json
from pathlib import Path, PureWindowsPath
import re


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def verify(root, manifest):
    root = Path(root).resolve()
    failures, seen = [], set()
    records = manifest.get('artifacts') if isinstance(manifest, dict) else None
    if not isinstance(records, list) or not records:
        return {'status': 'FAIL', 'checked': 0, 'failures': [{'error': 'nonempty_artifacts_list_required'}]}
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get('path'), str) or not record['path']:
            failures.append({'error': 'invalid_record'}); continue
        rel = record['path']
        path = (root / rel).resolve()
        if Path(rel).is_absolute() or PureWindowsPath(rel).is_absolute() or not path.is_relative_to(root):
            failures.append({'path': rel, 'error': 'outside_root'}); continue
        identity = str(path)
        if identity in seen:
            failures.append({'path': rel, 'error': 'duplicate_path'}); continue
        seen.add(identity)
        expected = record.get('sha256')
        if not isinstance(expected, str) or not re.fullmatch(r'[a-fA-F0-9]{64}', expected):
            failures.append({'path': rel, 'error': 'invalid_sha256'}); continue
        if not path.is_file():
            failures.append({'path': rel, 'error': 'missing'}); continue
        size = record.get('bytes')
        if size is not None and (type(size) is not int or size < 0 or path.stat().st_size != size):
            failures.append({'path': rel, 'error': 'size_mismatch'}); continue
        try:
            actual = digest(path)
        except OSError:
            failures.append({'path': rel, 'error': 'unreadable'}); continue
        if actual != expected.lower():
            failures.append({'path': rel, 'error': 'hash_mismatch', 'actual': actual})
    return {'status': 'PASS' if not failures else 'FAIL', 'checked': len(records), 'failures': failures}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--root', type=Path, required=True, help='Allowed root for manifest-relative paths')
    parser.add_argument('--output', type=Path, help='Optional JSON result file')
    args = parser.parse_args()
    try:
        result = verify(args.root, json.loads(args.manifest.read_text(encoding='utf-8')))
        if args.output:
            args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({'status': 'ERROR', 'error': str(exc)}))
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
