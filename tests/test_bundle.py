import contextlib
import csv
import hashlib
from importlib import metadata
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from oss_license_checker.bundle import create_bundle
from oss_license_checker.cli import main


def install(root, files, declared=(), name='demo'):
    info = root / f'{name}-1.0.dist-info'
    info.mkdir(parents=True)
    (info / 'METADATA').write_text('Metadata-Version: 2.4\nName: ' + name + '\nVersion: 1.0\nLicense-Expression: MIT\n'
                                 + ''.join(f'License-File: {value}\n' for value in declared))
    for source, data in files.items():
        path = root / source
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    for source in files:
        writer.writerow([source, '', ''])
    (info / 'RECORD').write_text(stream.getvalue())
    return metadata.Distribution.at(info)


def row(name='demo'):
    return {'name': name, 'version': '1.0', 'license': 'MIT', 'source': 'License-Expression', 'status': 'allowed'}


class BundleTests(unittest.TestCase):
    @patch('oss_license_checker.bundle.metadata.distributions')
    def test_only_selected_packages_are_bundled(self, distributions):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            distributions.return_value = [install(root, {'demo/LICENSE': b'MIT'}),
                                           install(root, {'other/LICENSE': b'Other license'}, name='other')]
            target = root / 'bundle.zip'
            self.assertFalse(create_bundle([row()], target))
            with zipfile.ZipFile(target) as archive:
                self.assertEqual(len(json.loads(archive.read('manifest.json'))['packages']), 1)
                self.assertFalse(any('other' in name for name in archive.namelist()))

    @patch('oss_license_checker.bundle.metadata.distributions')
    def test_standard_pep639_and_legacy_files_preserve_bytes_and_hashes(self, distributions):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = b'Copyright\r\n\xff\x00'
            files = {'demo-1.0.dist-info/licenses/legal.txt': payload,
                     'demo-1.0.dist-info/NOTICE': b'Notice', 'demo/COPYING.LESSER': b'License',
                     'demo/LICENSE-MIT': b'MIT', 'demo/module.py': b'not evidence'}
            distributions.return_value = [install(root, files, declared=['legal.txt'])]
            target = root / 'bundle.zip'
            self.assertFalse(create_bundle([row()], target))
            with zipfile.ZipFile(target) as archive:
                package = json.loads(archive.read('manifest.json'))['packages'][0]
                self.assertEqual(package['evidence_status'], 'collected')
                self.assertEqual(package['missing_declared_files'], [])
                self.assertEqual(len(package['files']), 4)
                for entry in package['files']:
                    data = archive.read(entry['path'])
                    self.assertEqual(data, files[entry['source']])
                    self.assertEqual(entry['sha256'], hashlib.sha256(data).hexdigest())
                    self.assertEqual(entry['size'], len(data))

    @patch('oss_license_checker.bundle.metadata.distributions')
    def test_missing_declared_files_and_missing_record_are_visible(self, distributions):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dist = install(root, {}, declared=['missing.txt'])
            (root / 'demo-1.0.dist-info/RECORD').unlink()
            distributions.return_value = [dist]
            target = root / 'bundle.zip'
            self.assertTrue(create_bundle([row()], target))
            with zipfile.ZipFile(target) as archive:
                package = json.loads(archive.read('manifest.json'))['packages'][0]
                self.assertEqual(package['missing_declared_files'], ['missing.txt'])
                self.assertEqual(package['files'], [])

    @patch('oss_license_checker.bundle.metadata.distributions')
    def test_path_traversal_symlinks_and_unreadable_files_leave_old_bundle_intact(self, distributions):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / 'bundle.zip'
            target.write_bytes(b'existing bundle')
            site = root / 'site'
            dist = install(site, {'demo/LICENSE': b'MIT'})
            distributions.return_value = [dist]
            with patch('oss_license_checker.bundle.Path.read_bytes', side_effect=PermissionError('unreadable')):
                with self.assertRaises(OSError):
                    create_bundle([row()], target)
            (site / 'demo/LICENSE').unlink()
            secret = root / 'LICENSE'
            secret.write_bytes(b'outside installation')
            (site / 'demo/LICENSE').symlink_to(secret)
            with self.assertRaisesRegex(ValueError, 'escapes installation'):
                create_bundle([row()], target)
            (site / 'demo-1.0.dist-info/RECORD').write_text('../LICENSE,,\n')
            with self.assertRaisesRegex(ValueError, 'Unsafe'):
                create_bundle([row()], target)
            self.assertEqual(target.read_bytes(), b'existing bundle')

    @patch('oss_license_checker.bundle.metadata.distributions')
    def test_malicious_license_file_declaration_is_rejected(self, distributions):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            distributions.return_value = [install(root, {}, declared=['../../LICENSE'])]
            with self.assertRaisesRegex(ValueError, 'Unsafe'):
                create_bundle([row()], root / 'bundle.zip')

    @patch('oss_license_checker.bundle.metadata.distributions')
    def test_output_cannot_replace_source_evidence(self, distributions):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            distributions.return_value = [install(root, {'demo/LICENSE': b'MIT'})]
            with self.assertRaisesRegex(ValueError, 'source license file'):
                create_bundle([row()], root / 'demo/LICENSE')
            self.assertEqual((root / 'demo/LICENSE').read_bytes(), b'MIT')

    @patch('oss_license_checker.bundle.metadata.distributions')
    def test_cli_collects_even_on_policy_failure_and_missing_evidence_fails_when_requested(self, distributions):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            distributions.return_value = [install(root, {'demo/LICENSE': b'MIT'})]
            target = root / 'bundle.zip'
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(['demo', '--deny', 'MIT', '--license-bundle', str(target)]), 1)
                self.assertTrue(target.exists())
                distributions.return_value = [install(root / 'missing', {})]
                self.assertEqual(main(['demo', '--license-bundle', str(target)]), 0)
                self.assertEqual(main(['demo', '--license-bundle', str(target), '--fail-missing-license-files']), 1)
                self.assertEqual(main(['--fail-missing-license-files']), 2)
                self.assertEqual(main(['--license-bundle', str(target), '--output', str(target)]), 2)
