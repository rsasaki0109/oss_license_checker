"""Acceptance cases for distinguishing inventory, policy and distribution readiness."""

import contextlib
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from oss_license_checker.cli import collect, main, render
from test_cli import distribution


class PurposeAcceptanceTests(unittest.TestCase):
    @patch('oss_license_checker.cli.metadata.distributions')
    def test_inventory_does_not_claim_an_unconfigured_policy_was_checked(self, distributions):
        distributions.return_value = [distribution('demo', 'MIT')]
        rows, failed = collect()
        self.assertFalse(failed)
        self.assertEqual(rows[0]['assessment'], 'inventory-only')
        self.assertIn('no allow/deny policy evaluated', rows[0]['reason'])
        self.assertEqual(json.loads(render(rows, 'json'))[0]['assessment'], 'inventory-only')
        self.assertEqual(next(csv.DictReader(io.StringIO(render(rows, 'csv'))))['assessment'], 'inventory-only')
        for format in ['html', 'markdown']:
            report = render(rows, format)
            self.assertNotIn('Policy check passed', report)
            self.assertIn('Distribution readiness: not assessed.', report)
            self.assertIn('installed Python distribution metadata', report)

    @patch('oss_license_checker.cli.metadata.distributions')
    def test_matching_an_explicit_policy_is_not_distribution_readiness(self, distributions):
        distributions.return_value = [distribution('demo', 'MIT')]
        rows, failed = collect(allow=['MIT'])
        self.assertFalse(failed)
        self.assertEqual(rows[0]['assessment'], 'policy-evaluated')
        for format in ['html', 'markdown']:
            report = render(rows, format, policy={'allow': ['MIT']})
            self.assertIn('Policy check passed', report)
            self.assertIn('Distribution readiness: not assessed.', report)

    @patch('oss_license_checker.cli.metadata.distributions')
    def test_unknown_remains_unreviewed_even_if_default_exit_is_zero(self, distributions):
        distributions.return_value = [distribution('demo')]
        for strict in [False, True]:
            rows, failed = collect(fail_unknown=strict)
            self.assertEqual(failed, strict)
            self.assertEqual(rows[0]['status'], 'unknown')
            self.assertEqual(rows[0]['assessment'], 'inventory-only')
        report = render(rows, 'html')
        self.assertIn('Inventory collected', report)
        self.assertIn('unknown', report)

    @patch('oss_license_checker.cli.create_bundle')
    @patch('oss_license_checker.cli.metadata.distributions')
    def test_missing_or_collected_files_do_not_imply_readiness(self, distributions, bundle):
        distributions.return_value = [distribution('demo', 'MIT')]
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / 'report.html'
            for missing in [False, True]:
                bundle.return_value = missing
                with contextlib.redirect_stderr(io.StringIO()):
                    code = main(['demo', '--allow', 'MIT', '--license-bundle', str(Path(directory) / 'licenses.zip'),
                                 '--fail-missing-license-files', '--format', 'html', '--output', str(report)])
                self.assertEqual(code, int(missing))
                self.assertIn('Distribution readiness: not assessed.', report.read_text())
