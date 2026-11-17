import contextlib
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from oss_license_checker.cli import main
from oss_license_checker.output import validate_output_paths, write_report
from test_cli import distribution


class OutputTests(unittest.TestCase):
    def test_config_baseline_and_output_collisions_include_aliases(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'input'
            source.write_text('original')
            symlink, hardlink = root / 'symlink', root / 'hardlink'
            symlink.symlink_to(source)
            hardlink.hardlink_to(source)
            for destination in [source, root / './input', symlink, hardlink]:
                for kwargs in [dict(report=destination, config=source), dict(report=destination, baseline=source),
                               dict(bundle=destination, config=source), dict(bundle=destination, baseline=source),
                               dict(report=destination, bundle=source)]:
                    with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                        validate_output_paths(**kwargs)
            self.assertEqual(source.read_text(), 'original')

    @patch('oss_license_checker.cli.metadata.distributions')
    def test_cli_does_not_overwrite_config(self, distributions):
        distributions.return_value = [distribution('demo', 'MIT')]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'policy.toml'
            text = 'allow = ["MIT"]\n'
            path.write_text(text)
            error = io.StringIO()
            with contextlib.redirect_stderr(error):
                self.assertEqual(main(['demo', '--config', str(path), '--output', str(path)]), 2)
            distributions.assert_not_called()
            self.assertIn('config', error.getvalue())
            self.assertEqual(path.read_text(), text)

    def test_failed_replacement_keeps_existing_report_and_removes_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / 'report.json'
            report.write_text('previous successful report')
            with patch('oss_license_checker.output.os.replace', side_effect=OSError('disk failure')):
                with self.assertRaises(OSError):
                    write_report(report, 'new report')
            self.assertEqual(report.read_text(), 'previous successful report')
            self.assertEqual(list(root.iterdir()), [report])

    def test_successful_write_updates_report_and_keeps_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / 'report.json'
            report.write_text('old')
            link = root / 'link.json'
            link.symlink_to(report)
            write_report(link, '日本語\n')
            self.assertTrue(link.is_symlink())
            self.assertEqual(report.read_text(), '日本語\n')
            self.assertEqual(len(list(root.iterdir())), 2)

    def test_partial_write_failure_keeps_previous_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / 'report.json'
            report.write_text('previous')
            original = tempfile.NamedTemporaryFile

            @contextlib.contextmanager
            def failing_file(**kwargs):
                with original(**kwargs) as stream:
                    def fail(text):
                        stream.write(text[:3])
                        raise OSError('disk full during write')
                    yield SimpleNamespace(name=stream.name, write=fail)

            with patch('oss_license_checker.output.tempfile.NamedTemporaryFile', failing_file):
                with self.assertRaises(OSError):
                    write_report(report, 'new report')
            self.assertEqual(report.read_text(), 'previous')
            self.assertEqual(list(root.iterdir()), [report])

    @patch('oss_license_checker.cli.metadata.distributions')
    def test_cli_reports_write_error_without_corrupting_previous_output(self, distributions):
        distributions.return_value = [distribution('demo', 'MIT')]
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / 'report.json'
            report.write_text('previous')
            with patch('oss_license_checker.output.os.replace', side_effect=OSError('write failed')), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(['demo', '--format', 'json', '--output', str(report)]), 2)
            self.assertEqual(report.read_text(), 'previous')
