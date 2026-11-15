import contextlib
import io
import json
import unittest
from email.message import Message
from types import SimpleNamespace
from unittest.mock import patch

from oss_license_checker.cli import collect, evaluate, main, render


def distribution(name, license=None, legacy=None):
    meta = Message()
    meta['Name'] = name
    if license:
        meta['License-Expression'] = license
    if legacy:
        meta['License'] = legacy
    return SimpleNamespace(metadata=meta, version='1.0')


class PolicyTests(unittest.TestCase):
    def test_alternative_and_combined_obligations(self):
        self.assertTrue(evaluate('MIT OR GPL-3.0-only', {'MIT'}, {'GPL-3.0-only'}))
        self.assertFalse(evaluate('MIT AND GPL-3.0-only', {'MIT'}, {'GPL-3.0-only'}))
        self.assertFalse(evaluate('(MIT OR Apache-2.0) AND GPL-3.0-only', {'MIT'}, set()))

    def test_exception_requires_explicit_permission(self):
        self.assertFalse(evaluate('Apache-2.0 WITH LLVM-exception', {'Apache-2.0'}, set()))
        self.assertTrue(evaluate('Apache-2.0 WITH LLVM-exception', {'Apache-2.0 WITH LLVM-exception'}, set()))
        self.assertFalse(evaluate('Apache-2.0 WITH LLVM-exception', set(), {'Apache-2.0'}))

    def test_malformed_expression(self):
        for value in ['', 'MIT OR', '(MIT', 'MIT Apache-2.0', 'MIT WITH OR', 'MIT OR (']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                evaluate(value, set(), set())

    @patch('oss_license_checker.cli.metadata.distributions')
    def test_inventory_unknown_and_normalization(self, distributions):
        distributions.return_value = [distribution('A_pkg', 'MIT'), distribution('b', legacy='License text\nCopyright')]
        rows, failed = collect(['a.pkg', 'b'], allow=['MIT'], fail_unknown=True)
        self.assertEqual([r['status'] for r in rows], ['allowed', 'unknown'])
        self.assertTrue(failed)
        self.assertEqual(json.loads(render(rows, 'json')), rows)
        self.assertIn('License text\nCopyright', render(rows, 'csv'))

    @patch('oss_license_checker.cli.metadata.distributions')
    def test_cli_exit_codes(self, distributions):
        distributions.return_value = [distribution('a', 'GPL-3.0-only'), distribution('b')]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['a', '--allow', 'MIT']), 1)
            self.assertEqual(main(['b', '--fail-unknown']), 1)
            self.assertEqual(main(['missing']), 2)
            self.assertEqual(main(['a']), 0)

    @patch('oss_license_checker.cli.metadata.distributions')
    def test_legacy_spdx_identifier_is_validated(self, distributions):
        distributions.return_value = [distribution('a', legacy='MIT')]
        self.assertEqual(collect()[0][0]['status'], 'allowed')
        self.assertEqual(collect(allow=['MIT'])[0][0]['status'], 'allowed')
        self.assertEqual(collect(deny=['MIT'])[0][0]['status'], 'denied')
        distributions.return_value = [distribution('a', legacy='mit'), distribution('b', legacy='MIT License')]
        self.assertEqual([r['status'] for r in collect()[0]], ['allowed', 'unknown'])

    @patch('oss_license_checker.cli.metadata.distributions')
    def test_classifier_only_metadata_stays_unknown_under_strict_policy(self, distributions):
        package = distribution('legacy')
        package.metadata['Classifier'] = 'License :: OSI Approved :: Apache Software License'
        distributions.return_value = [package]
        rows, failed = collect(fail_unknown=True)
        self.assertTrue(failed)
        self.assertEqual(rows[0]['status'], 'unknown')


if __name__ == '__main__':
    unittest.main()
