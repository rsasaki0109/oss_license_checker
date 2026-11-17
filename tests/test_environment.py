from importlib import metadata
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from oss_license_checker.cli import collect
from oss_license_checker.bundle import create_bundle
from oss_license_checker.environment import installed_distributions
from test_cli import distribution
from test_bundle import install, row


class EnvironmentTests(unittest.TestCase):
    @patch('oss_license_checker.cli.metadata.distributions')
    def test_first_distribution_wins_including_normalized_aliases(self, distributions):
        local = distribution('My_Pkg', 'MIT')
        local.version = '2.0'
        global_package = distribution('my-pkg', 'GPL-3.0-only')
        distributions.return_value = [local, global_package]
        rows, failed = collect(['my.pkg'], allow=['MIT'])
        self.assertFalse(failed)
        self.assertEqual(rows[0]['version'], '2.0')
        self.assertEqual(rows[0]['license'], 'MIT')

    @patch('oss_license_checker.cli.metadata.distributions')
    def test_recursive_dependencies_use_the_same_priority(self, distributions):
        app = distribution('app', 'MIT')
        app.metadata['Requires-Dist'] = 'child>=2'
        shadow_app = distribution('app', 'MIT')
        shadow_app.metadata['Requires-Dist'] = 'not-installed'
        child = distribution('child', 'MIT')
        child.version = '2.0'
        distributions.return_value = [app, child, shadow_app, distribution('child', 'GPL-3.0-only')]
        rows, failed = collect(['app'], recursive=True, allow=['MIT'])
        self.assertFalse(failed)
        self.assertEqual([r['name'] for r in rows], ['app', 'child'])
        self.assertEqual(rows[1]['version'], '2.0')

    @patch('oss_license_checker.bundle.metadata.distributions')
    def test_bundle_uses_first_distribution_even_if_shadow_has_same_version(self, distributions):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            local = install(root / 'local', {'demo/LICENSE': b'local evidence'})
            shadow = install(root / 'global', {'demo/LICENSE': b'shadow evidence'})
            distributions.return_value = [local, shadow]
            bundle = root / 'licenses.zip'
            self.assertFalse(create_bundle([row()], bundle))
            with zipfile.ZipFile(bundle) as archive:
                record = json.loads(archive.read('manifest.json'))['packages'][0]
                self.assertEqual(archive.read(record['files'][0]['path']), b'local evidence')

    def test_real_metadata_discovery_respects_search_path_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            local = root / 'local'
            shadow = root / 'shadow'
            install(local, {'demo/LICENSE': b'local'})
            install(shadow, {'demo/LICENSE': b'shadow'})
            installed = installed_distributions(metadata.distributions(path=[str(local), str(shadow)]))
            self.assertEqual(Path(installed['demo'].locate_file('')).resolve(), local.resolve())
            reversed_order = installed_distributions(metadata.distributions(path=[str(shadow), str(local)]))
            self.assertEqual(Path(reversed_order['demo'].locate_file('')).resolve(), shadow.resolve())
