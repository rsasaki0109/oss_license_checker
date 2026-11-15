"""Composite action driver. Inputs travel through argv, never shell interpolation."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile


def boolean(env, name):
    value = env.get(name, 'false').lower()
    if value not in {'true', 'false'}:
        raise ValueError(f'{name} must be true or false')
    return value == 'true'


def run(env):
    code, outputs = 2, {}
    try:
        parent = env.get('CHECKER_OUTPUT_DIRECTORY', 'license-reports')
        if not parent.strip() or '\n' in parent or '\r' in parent:
            raise ValueError('Output directory must be nonempty and contain no newlines')
        parent = Path(parent).resolve()
        parent.mkdir(parents=True, exist_ok=True)
        directory = Path(tempfile.mkdtemp(prefix='scan-', dir=parent))
        report, bundle = directory / 'licenses.md', directory / 'licenses.zip'
        outputs = {'report-path': str(report), 'bundle-path': str(bundle)}
        packages = [value.strip() for value in env.get('CHECKER_PACKAGES', '').splitlines() if value.strip()]
        if any(value.startswith('-') for value in packages):
            raise ValueError('Package names must not start with a dash')
        args = [env.get('CHECKER_PYTHON', sys.executable), '-m', 'oss_license_checker.cli',
                '--format', 'markdown', '--output', str(report), '--license-bundle', str(bundle)]
        for setting, flag in [('CHECKER_RECURSIVE', '--recursive'), ('CHECKER_FAIL_ON_CHANGE', '--fail-on-change'),
                              ('CHECKER_FAIL_MISSING', '--fail-missing-license-files')]:
            if boolean(env, setting):
                args.append(flag)
        unknown = env.get('CHECKER_FAIL_UNKNOWN', 'inherit').lower()
        if unknown not in {'true', 'false', 'inherit'}:
            raise ValueError('CHECKER_FAIL_UNKNOWN must be true, false or inherit')
        if unknown != 'inherit':
            args.append('--fail-unknown' if unknown == 'true' else '--no-fail-unknown')
        for setting, flag in [('CHECKER_CONFIG', '--config'), ('CHECKER_BASELINE', '--baseline')]:
            if env.get(setting):
                args.extend([flag, env[setting]])
        args.extend(['--', *packages])
        result = subprocess.run(args, check=False)
        code = result.returncode if result.returncode in {0, 1, 2} else 2
        if report.exists() and env.get('GITHUB_STEP_SUMMARY'):
            with Path(env['GITHUB_STEP_SUMMARY']).open('a', encoding='utf-8') as stream:
                stream.write(report.read_text(encoding='utf-8'))
    except (ValueError, OSError) as exc:
        print(f'Action error: {exc}', file=sys.stderr)
        code = 2
    outputs['exit-code'] = str(code)
    with Path(env['GITHUB_OUTPUT']).open('a', encoding='utf-8') as stream:
        for key, value in outputs.items():
            stream.write(f'{key}={value}\n')
    # The composite's final gate fails after artifact upload, including on scan errors.
    return 0


if __name__ == '__main__':
    sys.exit(run(os.environ))
