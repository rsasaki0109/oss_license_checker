"""Exercise a preinstalled real project in an isolated Python environment."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', required=True)
    parser.add_argument('--project', choices=['requests', 'httpx', 'rich'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    args.output.mkdir(parents=True, exist_ok=True)
    output = args.output.resolve()
    base = [str(Path(args.python).absolute()), '-I', '-m', 'oss_license_checker', args.project, '--recursive',
            '--config', str(root / 'examples/validation' / args.project / 'policy.toml')]

    def check(arguments, expected=0):
        result = subprocess.run([*base, *arguments], capture_output=True, text=True)
        if result.returncode != expected:
            raise RuntimeError(f'Expected exit {expected}, got {result.returncode}: {result.stderr}')
        return result

    inventory = output / 'inventory.json'
    bundle = output / 'licenses.zip'
    check(['--format', 'json', '--output', str(inventory), '--license-bundle', str(bundle), '--fail-missing-license-files'])
    rows = json.loads(inventory.read_text())
    assert rows and all(row['status'] == 'allowed' for row in rows)
    with zipfile.ZipFile(bundle) as archive:
        packages = json.loads(archive.read('manifest.json'))['packages']
        for package in packages:
            assert package['evidence_status'] == 'collected'
            for file in package['files']:
                assert hashlib.sha256(archive.read(file['path'])).hexdigest() == file['sha256']
    check(['--baseline', str(inventory), '--fail-on-change', '--format', 'json', '--output', str(output / 'unchanged.json')])
    assert json.loads((output / 'unchanged.json').read_text())['changes'] == []
    modified = json.loads(inventory.read_text())
    modified[0]['version'] = 'baseline-version-for-change-test'
    changed = output / 'changed-baseline.json'
    changed.write_text(json.dumps(modified))
    check(['--baseline', str(changed), '--fail-on-change', '--format', 'html', '--output', str(output / 'changes.html')], 1)
    check(['--format', 'markdown', '--output', str(output / 'licenses.md')])
    denied = [item for license in ['MIT', 'Apache-2.0', 'BSD-2-Clause', 'BSD-3-Clause', 'MPL-2.0', 'PSF-2.0']
              for item in ['--deny', license]]
    check([*denied, '--format', 'json', '--output', str(output / 'denied.json')], 1)
    summary = {'project': args.project, 'versions': {row['name']: row['version'] for row in rows},
               'statuses': dict(Counter(row['status'] for row in rows)),
               'evidence_files': sum(len(package['files']) for package in packages),
               'checks': ['strict-policy', 'evidence-and-hashes', 'unchanged-baseline', 'changed-baseline', 'markdown', 'deny-policy']}
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
