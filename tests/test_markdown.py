import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from oss_license_checker.cli import main, render
from oss_license_checker.baseline import compare, render_comparison
from oss_license_checker.markdown import literal
from test_cli import distribution


def row(**values):
    return {'name': 'demo', 'version': '1.0', 'license': 'MIT', 'source': 'License-Expression',
            'status': 'allowed', **values}


class MarkdownTests(unittest.TestCase):
    def test_inventory_summary_and_review_evidence(self):
        text = render([row(), row(name='other', status='unknown', override_reason='Reviewed release LICENSE')],
                      'markdown', policy={'allow': ['MIT'], 'fail-unknown': True}, scope='demo and dependencies')
        self.assertIn('**Policy check failed**', text)
        self.assertIn('| 2 | 1 | 0 | 1 |', text)
        self.assertIn('Reviewed release LICENSE', text)
        self.assertIn('demo and dependencies', text)

    def test_untrusted_metadata_cannot_break_table_or_inject_markup(self):
        payload = '<script>bad</script> | [click](javascript:bad) `code`\n# heading'
        escaped = literal(payload)
        self.assertNotIn('|', escaped)
        self.assertNotIn('<script>', escaped)
        self.assertNotIn('[click]', escaped)
        self.assertNotIn('`', escaped)
        self.assertIn('<br>', escaped)
        text = render([row(license=payload, effective_license=payload, override_reason=payload)], 'markdown', scope=payload)
        # Header, separator and one data row remain the only inventory lines.
        inventory = text.split('## Package inventory')[1].strip().split('\n\n')[0]
        self.assertEqual(len(inventory.splitlines()), 3)
        self.assertTrue(all(line.count('|') == 9 for line in inventory.splitlines()))

    def test_change_failure_and_old_new_values(self):
        before, after = [row()], [row(license='GPL-3.0-only', status='denied')]
        changes = compare(before, after)
        text = render_comparison(after, changes, 'markdown', policy={}, scope=None, fail_on_change=True)
        self.assertIn('Policy check failed', text)
        self.assertIn('## Changes from baseline', text)
        self.assertIn('Before | After', text)
        self.assertIn('GPL&#45;3&#46;0&#45;only', text)
        text = render_comparison([row(version='2.0')], compare(before, [row(version='2.0')]),
                                 'markdown', policy={}, scope=None, fail_on_change=True)
        self.assertIn('Change check failed', text)

    def test_empty_inventory_and_unchanged_baseline(self):
        self.assertIn('No installed packages', render([], 'markdown'))
        text = render_comparison([row()], [], 'markdown', policy={}, scope=None, fail_on_change=True)
        self.assertIn('No package changes.', text)
        self.assertIn('Inventory collected (no allow/deny policy)', text)

    @patch('oss_license_checker.cli.metadata.distributions')
    def test_cli_writes_markdown_despite_policy_failure(self, distributions):
        distributions.return_value = [distribution('demo', 'MIT')]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'report.md'
            self.assertEqual(main(['demo', '--deny', 'MIT', '--format', 'markdown', '--output', str(path)]), 1)
            self.assertIn('Policy check failed', path.read_text())
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(['demo', '--format', 'markdown']), 0)
            self.assertIn('# OSS License Checker', output.getvalue())
