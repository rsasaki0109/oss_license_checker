import contextlib
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from oss_license_checker.baseline import compare
from oss_license_checker.cli import collect, main, render
from oss_license_checker.overrides import validate_overrides
from test_cli import distribution


def review(**values):
    return {'license': 'MIT', 'version': '1.0', 'reason': 'Reviewed upstream LICENSE at release 1.0', **values}


class OverrideTests(unittest.TestCase):
    @patch('oss_license_checker.cli.metadata.distributions')
    def test_missing_metadata_is_reviewable_and_original_evidence_is_preserved(self, distributions):
        distributions.return_value = [distribution('My_Pkg')]
        rows, failed = collect(allow=['MIT'], fail_unknown=True, overrides={'my.pkg': review()})
        self.assertFalse(failed)
        self.assertEqual(rows[0]['status'], 'allowed')
        self.assertEqual(rows[0]['license'], 'UNKNOWN')
        self.assertEqual(rows[0]['source'], 'missing')
        self.assertEqual(rows[0]['effective_license'], 'MIT')
        self.assertIn('Reviewed upstream', rows[0]['override_reason'])
        self.assertIn('Reviewed override:', render(rows, 'html'))
        csv_rows = list(csv.DictReader(io.StringIO(render(rows, 'csv'))))
        self.assertEqual(csv_rows[0]['effective_license'], 'MIT')

    @patch('oss_license_checker.cli.metadata.distributions')
    def test_override_is_not_a_policy_bypass(self, distributions):
        distributions.return_value = [distribution('demo')]
        rows, failed = collect(deny=['GPL-3.0-only'], overrides={'demo': review(license='GPL-3.0-only')})
        self.assertTrue(failed)
        self.assertEqual(rows[0]['status'], 'denied')
        rows, failed = collect(fail_unknown=True, overrides={'demo': review(license='LicenseRef-Internal')})
        self.assertTrue(failed)
        self.assertEqual(rows[0]['status'], 'unknown')

    @patch('oss_license_checker.cli.metadata.distributions')
    def test_override_expires_when_version_changes(self, distributions):
        distributions.return_value = [distribution('demo')]
        with self.assertRaisesRegex(ValueError, 'review the license again'):
            collect(overrides={'demo': review(version='0.9')})

    def test_invalid_override_schema_identifiers_and_duplicates(self):
        invalid = [None, [], {'demo': {}}, {'demo': review(version='>=1')},
                   {'demo': review(license='MadeUp')}, {'demo': review(reason=' ')},
                   {'demo': review(version=1)}, {'demo': {**review(), 'typo': True}},
                   {'bad/name': review()}, {'my_pkg': review(), 'my-pkg': review()}]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_overrides(value)

    @patch('oss_license_checker.cli.metadata.distributions')
    def test_only_selected_packages_apply_overrides(self, distributions):
        distributions.return_value = [distribution('demo', 'MIT')]
        rows, failed = collect(['demo'], overrides={'other': review(version='0.1')})
        self.assertFalse(failed)
        self.assertEqual(rows[0]['override_reason'], '')

    @patch('oss_license_checker.cli.metadata.distributions')
    def test_effective_license_change_is_detected_and_old_baselines_still_work(self, distributions):
        distributions.return_value = [distribution('demo')]
        before = collect()[0]
        after = collect(overrides={'demo': review()})[0]
        self.assertIn('effective_license', compare(before, after)[0]['fields'])
        legacy = [{key: value for key, value in row.items() if key not in {'effective_license', 'override_reason'}} for row in before]
        self.assertEqual(compare(legacy, before), [])

    @patch('oss_license_checker.cli.metadata.distributions')
    def test_cli_pyproject_and_dedicated_file(self, distributions):
        distributions.return_value = [distribution('demo')]
        with tempfile.TemporaryDirectory() as directory:
            for filename, prefix in [('policy.toml', ''), ('pyproject.toml', 'tool.oss-license-checker.')]:
                path = Path(directory) / filename
                path.write_text((f'[{prefix[:-1]}]\n' if prefix else '') + 'allow = ["MIT"]\nfail-unknown = true\n'
                                + f'[{prefix}overrides.demo]\nlicense = "mit"\nversion = "1.0"\nreason = "Reviewed LICENSE"\n')
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(main(['demo', '--config', str(path), '--format', 'json']), 0)
                self.assertEqual(json.loads(output.getvalue())[0]['effective_license'], 'MIT')
                path.write_text(path.read_text().replace('version = "1.0"', 'version = "0.9"'))
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(main(['demo', '--config', str(path)]), 2)
