import contextlib
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from oss_license_checker.baseline import compare, load_baseline, render_comparison
from oss_license_checker.cli import main
from test_cli import distribution


def row(name='demo', **values):
    return {'name': name, 'version': '1.0', 'license': 'MIT', 'source': 'License-Expression',
            'status': 'allowed', **values}


class BaselineTests(unittest.TestCase):
    def test_add_remove_and_multiple_changed_fields(self):
        before = [row('removed'), row('changed')]
        after = [row('added'), row('changed', version='2.0', license='GPL-3.0-only', status='denied')]
        changes = compare(before, after)
        self.assertEqual([item['change'] for item in changes], ['added', 'changed', 'removed'])
        self.assertEqual(changes[1]['fields'], ['version', 'license', 'status', 'effective_license'])
        self.assertEqual(changes[1]['before']['license'], 'MIT')
        self.assertEqual(changes[1]['after']['license'], 'GPL-3.0-only')

    def test_name_normalization_and_reason_changes_do_not_trigger_diff(self):
        self.assertEqual(compare([row('My_Package', reason='old')], [row('my.package', reason='new')]), [])
        self.assertEqual(compare([], []), [])

    def test_invalid_inventory_and_normalized_duplicates(self):
        for value in [None, {}, [None], [{}], [row(status='bad')], [row(version=1)],
                      [row('bad/name')], [row('my_pkg'), row('my-pkg')]]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                compare(value, [])

    def test_load_inventory_and_previous_comparison(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'baseline.json'
            for value in [[row()], {'packages': [row()], 'changes': []}]:
                path.write_text(json.dumps(value))
                self.assertEqual(load_baseline(path), [row()])

    def test_render_all_formats_and_escape_html(self):
        payload = '<script>alert("bad")</script>\n日本語'
        before, after = [row()], [row(license=payload, status='unknown')]
        changes = compare(before, after)
        options = {'policy': {}, 'scope': 'demo', 'fail_on_change': True}
        parsed = json.loads(render_comparison(after, changes, 'json', **options))
        self.assertEqual(parsed['changes'][0]['after']['license'], payload)
        csv_rows = list(csv.DictReader(io.StringIO(render_comparison(after, changes, 'csv', **options))))
        self.assertEqual(json.loads(csv_rows[0]['after'])['license'], payload)
        html = render_comparison(after, changes, 'html', **options)
        self.assertIn('Change check failed', html)
        self.assertIn('Changes from baseline', html)
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertIn('1 package changes', render_comparison(after, changes, 'table', **options))

    @patch('oss_license_checker.cli.metadata.distributions')
    def test_cli_changes_and_exit_codes(self, distributions):
        distributions.return_value = [distribution('demo', 'MIT')]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'baseline.json'
            path.write_text('[]')
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(['demo', '--baseline', str(path), '--format', 'json']), 0)
            document = json.loads(output.getvalue())
            self.assertEqual(document['changes'][0]['change'], 'added')
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['demo', '--baseline', str(path), '--fail-on-change']), 1)
            # A comparison can be reused as the next baseline, without reason-key noise.
            path.write_text(json.dumps(document))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['demo', '--baseline', str(path), '--fail-on-change']), 0)

    @patch('oss_license_checker.cli.metadata.distributions')
    def test_policy_still_fails_when_baseline_contains_same_violation(self, distributions):
        distributions.return_value = [distribution('demo', 'GPL-3.0-only')]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'baseline.json'
            path.write_text(json.dumps([row(license='GPL-3.0-only', status='denied')]))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(['demo', '--allow', 'MIT', '--baseline', str(path), '--format', 'json']), 1)
            self.assertEqual(json.loads(output.getvalue())['changes'], [])

    @patch('oss_license_checker.cli.metadata.distributions')
    def test_fail_on_change_writes_report_and_errors_preserve_baseline(self, distributions):
        distributions.return_value = [distribution('demo', 'MIT')]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'baseline.json'
            target = Path(directory) / 'report.html'
            path.write_text('[]')
            self.assertEqual(main(['demo', '--baseline', str(path), '--fail-on-change', '--format', 'html', '--output', str(target)]), 1)
            self.assertIn('Change check failed', target.read_text())
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(['--fail-on-change']), 2)
                self.assertEqual(main(['--baseline', str(path), '--output', str(path)]), 2)
                self.assertEqual(path.read_text(), '[]')
                path.write_text('not json')
                self.assertEqual(main(['--baseline', str(path)]), 2)
