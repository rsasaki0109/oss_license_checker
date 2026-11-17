"""Protect input files and publish completed reports atomically."""

import os
from pathlib import Path
import tempfile


def same_file(left, right):
    if left.resolve() == right.resolve():
        return True
    return left.exists() and right.exists() and left.samefile(right)


def validate_output_paths(report=None, bundle=None, config=None, baseline=None):
    outputs = [('Report', report), ('License bundle', bundle)]
    for label, destination in outputs:
        if destination is None:
            continue
        for source_label, source in [('config', config), ('baseline', baseline)]:
            if source is not None and same_file(destination, source):
                raise ValueError(f'{label} output must differ from {source_label} input')
    if report is not None and bundle is not None and same_file(report, bundle):
        raise ValueError('Report and license bundle outputs must be different files')


def write_report(path, text):
    target = path.resolve()
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=target.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(text)
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
