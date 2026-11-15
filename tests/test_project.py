import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from oss_license_checker.cli import collect, main
from oss_license_checker.project import dependency_names, load_policy
from test_cli import distribution


def package(name, requires=(), extras=()):
    dist = distribution(name, 'MIT')
    for requirement in requires:
        dist.metadata['Requires-Dist'] = requirement
    for extra in extras:
        dist.metadata['Provides-Extra'] = extra
    return dist


class DependencyTests(unittest.TestCase):
    def test_transitive_markers_cycles_and_unrelated_packages(self):
        installed = {
            'app': package('app', ['child>=1', 'absent; python_version < "2"']),
            'child': package('child', ['app', 'leaf']),
            'leaf': package('leaf'),
            'unrelated': package('unrelated'),
        }
        self.assertEqual(dependency_names(installed, ['app']), ['app', 'child', 'leaf'])

    def test_extras_propagate_and_revisit_shared_dependency(self):
        installed = {
            'app': package('app', ['shared[fast]', 'shared']),
            'shared': package('shared', ['speed; extra == "fast"', 'base'], ['fast']),
            'speed': package('speed'), 'base': package('base'),
        }
        self.assertEqual(dependency_names(installed, ['app']), ['app', 'base', 'shared', 'speed'])
        self.assertEqual(dependency_names(installed, ['shared']), ['base', 'shared'])

    def test_root_extras_and_canonical_names(self):
        installed = {'my-app': package('My_App', ['child; extra == "http-2"'], ['http_2']), 'child': package('child')}
        self.assertEqual(dependency_names(installed, ['my.app[http_2]']), ['child', 'my-app'])

    def test_broken_environment_and_invalid_requirements(self):
        scenarios = [
            ({'app': package('app', ['missing'])}, ['app']),
            ({'app': package('app', ['child>=2']), 'child': package('child')}, ['app']),
            ({'app': package('app')}, ['app[missing]']),
            ({'app': package('app', ['???'])}, ['app']),
            ({}, []), ({}, ['???']),
        ]
        for installed, roots in scenarios:
            with self.subTest(roots=roots, installed=installed), self.assertRaises(ValueError):
                dependency_names(installed, roots)

    @patch('oss_license_checker.cli.metadata.distributions')
    def test_recursive_cli_reports_transitive_violation(self, distributions):
        distributions.return_value = [package('app', ['child']), distribution('child', 'GPL-3.0-only')]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(['app', '--recursive', '--allow', 'MIT', '--format', 'json']), 1)
        self.assertEqual([row['status'] for row in json.loads(output.getvalue())], ['allowed', 'denied'])
        self.assertEqual(len(collect(['app'])[0]), 1)


class ConfigTests(unittest.TestCase):
    def test_explicit_policy_and_pyproject(self):
        with tempfile.TemporaryDirectory() as directory:
            for filename, heading in [('policy.toml', ''), ('pyproject.toml', '[tool.oss-license-checker]\n')]:
                path = Path(directory) / filename
                path.write_text(heading + 'allow = ["MIT"]\nfail-unknown = true\n')
                self.assertEqual(load_policy(path), {'allow': ['MIT'], 'fail-unknown': True})

    def test_invalid_policies_fail_with_exit_two(self):
        invalid = ['allow = "MIT"', 'deny = [123]', 'fail-unknown = "true"', 'typo = true', 'allow = [" "]', 'bad = [']
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'policy.toml'
            for text in invalid:
                path.write_text(text)
                with self.subTest(text=text), contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(main(['--config', str(path)]), 2)
            path = Path(directory) / 'pyproject.toml'
            path.write_text('[project]\nname = "app"')
            with self.assertRaises(ValueError):
                load_policy(path)
            path.write_text('tool = "invalid"')
            with self.assertRaises(ValueError):
                load_policy(path)

    @patch('oss_license_checker.cli.metadata.distributions')
    def test_cli_overrides_config_lists_and_unknown_switch(self, distributions):
        distributions.return_value = [distribution('app', 'MIT'), distribution('unknown')]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'policy.toml'
            path.write_text('allow = ["Apache-2.0"]\nfail-unknown = true')
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['app', '--config', str(path)]), 1)
                self.assertEqual(main(['app', '--config', str(path), '--allow', 'MIT']), 0)
                self.assertEqual(main(['unknown', '--config', str(path)]), 1)
                self.assertEqual(main(['unknown', '--config', str(path), '--no-fail-unknown']), 0)
