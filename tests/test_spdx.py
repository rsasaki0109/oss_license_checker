import contextlib
import io
import json
import unittest
from unittest.mock import patch

from oss_license_checker.cli import collect, evaluate, main, normalize_rules
from test_cli import distribution


class SPDXTests(unittest.TestCase):
    def test_unknown_identifiers_and_exceptions_fail_validation(self):
        for expression in ['Not-A-License', 'MIT WITH MadeUp-exception', 'MIT OR Not-A-License']:
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                evaluate(expression, set(), set())

    def test_case_normalization_preserves_policy_matching(self):
        self.assertTrue(evaluate('mit or apache-2.0', {'mIt'}, set()))
        self.assertFalse(evaluate('mit', {'MIT'}, {'mit'}))
        self.assertTrue(evaluate('apache-2.0 with llvm-exception', {'Apache-2.0 WITH LLVM-exception'}, set()))

    def test_invalid_policies_are_rejected_even_without_packages(self):
        for rule in ['M1T', 'MIT OR Apache-2.0', '(MIT)', 'MIT WITH MadeUp-exception']:
            with self.subTest(rule=rule), self.assertRaises(ValueError):
                collect(allow=[rule])
        self.assertEqual(normalize_rules(['mit', 'apache-2.0']), ['MIT', 'Apache-2.0'])

    def test_custom_licenses_require_explicit_review(self):
        with self.assertRaises(ValueError):
            evaluate('LicenseRef-Internal', set(), set())
        with self.assertRaises(ValueError):
            evaluate('MIT OR LicenseRef-Internal', {'MIT'}, set())
        self.assertTrue(evaluate('LicenseRef-Internal', {'LicenseRef-Internal'}, set()))
        self.assertFalse(evaluate('LicenseRef-Internal', set(), {'LicenseRef-Internal'}))

    def test_legacy_plus_and_deprecated_identifiers_remain_supported(self):
        self.assertTrue(evaluate('GPL-2.0+', {'GPL-2.0+'}, set()))
        self.assertTrue(evaluate('GPL-2.0', {'GPL-2.0'}, set()))

    @patch('oss_license_checker.cli.metadata.distributions')
    def test_invalid_metadata_is_unknown_and_evidence_is_preserved(self, distributions):
        distributions.return_value = [distribution('demo', 'MIT WITH MadeUp-exception')]
        rows, failed = collect(fail_unknown=True)
        self.assertTrue(failed)
        self.assertEqual(rows[0]['status'], 'unknown')
        self.assertEqual(rows[0]['license'], 'MIT WITH MadeUp-exception')
        self.assertIn('exception', rows[0]['reason'])

    @patch('oss_license_checker.cli.metadata.distributions')
    def test_cli_typo_is_configuration_error(self, distributions):
        distributions.return_value = [distribution('demo', 'MIT')]
        output, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            self.assertEqual(main(['--allow', 'M1T']), 2)
        self.assertEqual(output.getvalue(), '')
        self.assertIn('Invalid policy entry', error.getvalue())

    @patch('oss_license_checker.cli.metadata.distributions')
    def test_cli_normalizes_rules_and_reports_reason(self, distributions):
        distributions.return_value = [distribution('demo', 'mit')]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(['demo', '--allow', 'mit', '--format', 'json']), 0)
        result = json.loads(output.getvalue())[0]
        self.assertEqual(result['license'], 'mit')
        self.assertEqual(result['status'], 'allowed')
        self.assertIn('permitted', result['reason'])
