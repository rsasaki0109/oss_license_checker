import contextlib
import io
from importlib import metadata
import unittest
from unittest.mock import patch

from oss_license_checker.cli import main


class VersionTests(unittest.TestCase):
    @patch('oss_license_checker.cli.metadata.distributions')
    def test_version_uses_distribution_metadata_without_scanning(self, distributions):
        expected = metadata.version('oss-license-checker')
        output = io.StringIO()
        with contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as result:
            main(['--version'])
        self.assertEqual(result.exception.code, 0)
        self.assertEqual(output.getvalue().strip(), f'oss-license-checker {expected}')
        distributions.assert_not_called()
