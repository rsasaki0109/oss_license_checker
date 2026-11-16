"""Execute README's first bash block against the checked-out commit."""

import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    output = args.output.resolve()
    repository = Path(__file__).resolve().parents[1]
    readme = (repository / 'README.md').read_text(encoding='utf-8')
    commands = readme.split('```bash\n', 1)[1].split('```', 1)[0]
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repository, text=True).strip()
    env = dict(os.environ)
    # Redirect just this clone URL, so PRs test their checkout rather than main.
    # README commands remain unchanged; no persistent Git config is modified.
    index = int(env.get('GIT_CONFIG_COUNT', '0'))
    env.update({'GIT_CONFIG_COUNT': str(index + 1),
                f'GIT_CONFIG_KEY_{index}': f'url.{repository.as_uri()}.insteadOf',
                f'GIT_CONFIG_VALUE_{index}': 'https://github.com/rsasaki0109/oss_license_checker.git'})
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='oss-onboarding-') as temporary:
        result = subprocess.run(['bash', '-e', '-c', commands], cwd=temporary, env=env,
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        (output / 'run.log').write_text(result.stdout, encoding='utf-8')
        clone = Path(temporary) / 'oss_license_checker'
        report = clone / 'licenses.html'
        cloned_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=clone, text=True).strip() if (clone / '.git').exists() else None
        summary = {'platform': platform.platform(), 'python': platform.python_version(),
                   'commit': commit, 'cloned_commit': cloned_commit, 'exit_code': result.returncode,
                   'html_created': report.is_file(), 'seconds': round(time.monotonic() - started, 2),
                   'clone_source': 'local checkout via process-only Git URL rewrite'}
        if report.is_file():
            (output / 'licenses.html').write_bytes(report.read_bytes())
        (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(summary))
        if result.returncode or not report.is_file() or cloned_commit != commit:
            raise SystemExit('README onboarding failed; inspect run.log and summary.json')


if __name__ == '__main__':
    main()
