import contextlib
from html.parser import HTMLParser
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from oss_license_checker.cli import main, render
from test_cli import distribution


class Document(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.tags = []
        self.content = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def handle_data(self, value):
        self.content.append(value)


def row(status='allowed', **kwargs):
    return dict(name='demo', version='1.0', license='MIT', source='License-Expression', status=status, **kwargs)


class ReportTests(unittest.TestCase):
    def test_counts_and_effective_policy(self):
        text = render([row('allowed'), row('denied'), row('unknown')], 'html',
                      policy={'allow': ['MIT'], 'deny': ['GPL-3.0-only'], 'fail-unknown': True})
        self.assertIn('Policy check failed', text)
        self.assertIn('<strong>3</strong><span>Packages inspected', text)
        for label in ('Allowed', 'Denied', 'Unknown'):
            self.assertIn(f'<strong>1</strong><span>{label}', text)
        self.assertIn('GPL-3.0-only', text)
        self.assertIn('Fail the check', text)

    def test_unknown_verdict_matches_exit_policy(self):
        self.assertIn('Policy check passed', render([row('unknown')], 'html'))
        self.assertIn('Policy check failed', render([row('unknown')], 'html', policy={'fail-unknown': True}))
        self.assertIn('Policy check failed', render([row('denied')], 'html'))

    def test_metadata_scope_and_policy_are_escaped(self):
        payload = '<script>alert("unsafe")</script><img src=x onerror="alert(1)"> & 日本語'
        values = {key: payload for key in ('name', 'version', 'license', 'source', 'status')}
        text = render([values], 'html', scope=payload, policy={'allow': [payload], 'deny': [payload]})
        document = Document(text)
        self.assertIn(payload, ''.join(document.content))
        self.assertFalse(any(tag in {'script', 'img', 'iframe', 'link'} for tag, _ in document.tags))
        for _, attrs in document.tags:
            self.assertFalse(any(key.startswith('on') for key in attrs))
            self.assertNotIn('src', attrs)
        self.assertIn('Content-Security-Policy', text)

    def test_empty_report(self):
        text = render([], 'html')
        self.assertIn('No installed packages matched this scan.', text)
        self.assertIn('Policy check passed', text)

    @patch('oss_license_checker.cli.metadata.distributions')
    def test_cli_writes_html_even_on_violation_and_uses_effective_config(self, distributions):
        distributions.return_value = [distribution('demo', 'GPL-3.0-only')]
        with tempfile.TemporaryDirectory() as directory:
            policy = Path(directory) / 'policy.toml'
            policy.write_text('allow = ["Apache-2.0"]')
            target = Path(directory) / 'report.html'
            self.assertEqual(main(['demo', '--config', str(policy), '--allow', 'MIT',
                                   '--format', 'html', '--output', str(target)]), 1)
            text = target.read_text()
            self.assertIn('Policy check failed', text)
            self.assertIn('<code>MIT</code>', text)
            self.assertNotIn('Apache-2.0', text)
            self.assertIn('demo (selected packages only)', text)

    @patch('oss_license_checker.cli.metadata.distributions')
    def test_stdout_and_recursive_scope(self, distributions):
        distributions.return_value = [distribution('demo', 'MIT')]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(['demo', '--recursive', '--format', 'html']), 0)
        self.assertTrue(output.getvalue().startswith('<!doctype html>'))
        self.assertIn('including transitive dependencies', output.getvalue())
