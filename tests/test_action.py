import contextlib
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts.run_action import run


class ActionTests(unittest.TestCase):
    @patch('scripts.run_action.subprocess.run')
    def test_preserves_failure_and_publishes_summary_without_shell_parsing(self, execute):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env = {'GITHUB_OUTPUT': str(root / 'outputs'), 'GITHUB_STEP_SUMMARY': str(root / 'summary'),
                   'CHECKER_OUTPUT_DIRECTORY': str(root / 'reports'), 'CHECKER_PACKAGES': 'demo[extra]\nother',
                   'CHECKER_CONFIG': 'policy with spaces.toml', 'CHECKER_FAIL_UNKNOWN': 'true'}
            def scan(args, **kwargs):
                Path(args[args.index('--output') + 1]).write_text('# Policy failed\n')
                self.assertEqual(args[-3:], ['--', 'demo[extra]', 'other'])
                self.assertIn('policy with spaces.toml', args)
                self.assertIn('--fail-unknown', args)
                self.assertNotIn('shell', kwargs)
                return SimpleNamespace(returncode=1)
            execute.side_effect = scan
            self.assertEqual(run(env), 0)
            self.assertIn('exit-code=1', (root / 'outputs').read_text())
            self.assertEqual((root / 'summary').read_text(), '# Policy failed\n')

    @patch('scripts.run_action.subprocess.run')
    def test_error_before_scan_is_published_as_exit_two(self, execute):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for extra in [{'CHECKER_PACKAGES': '--deny'}, {'CHECKER_RECURSIVE': 'typo'},
                          {'CHECKER_FAIL_UNKNOWN': 'typo'}, {'CHECKER_OUTPUT_DIRECTORY': 'a\nforged=value'}]:
                output = root / 'outputs'
                env = {'GITHUB_OUTPUT': str(output), 'CHECKER_OUTPUT_DIRECTORY': str(root / 'reports'), **extra}
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(run(env), 0)
                self.assertIn('exit-code=2', output.read_text())
            execute.assert_not_called()

    @patch('scripts.run_action.subprocess.run')
    def test_each_run_has_unique_output_directory_and_inherits_policy(self, execute):
        execute.return_value = SimpleNamespace(returncode=0)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env = {'GITHUB_OUTPUT': str(root / 'outputs'), 'CHECKER_OUTPUT_DIRECTORY': str(root / 'reports')}
            run(env)
            run(env)
            first, second = [call.args[0] for call in execute.call_args_list]
            self.assertNotEqual(first[first.index('--output') + 1], second[second.index('--output') + 1])
            self.assertNotIn('--fail-unknown', first)
            self.assertNotIn('--no-fail-unknown', first)

    @patch('scripts.run_action.subprocess.run')
    def test_signal_and_execution_errors_map_to_exit_two(self, execute):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env = {'GITHUB_OUTPUT': str(root / 'outputs'), 'CHECKER_OUTPUT_DIRECTORY': str(root / 'reports')}
            execute.return_value = SimpleNamespace(returncode=-9)
            run(env)
            self.assertIn('exit-code=2', (root / 'outputs').read_text())
            execute.side_effect = OSError('cannot execute')
            with contextlib.redirect_stderr(io.StringIO()):
                run(env)
            self.assertTrue((root / 'outputs').read_text().endswith('exit-code=2\n'))
