import contextlib
from html import unescape
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from oss_license_checker.cli import main
from oss_license_checker.source import scan_source, render_source, review_draft
from oss_license_checker.source import load_source_baseline, source_changes
from scripts.validate_distribution_review import validate


class SourceReviewAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.git('init', '-q')
        for name, text in [('LICENSE', 'MIT'), ('docs/assets/LICENSE', 'BSD'), ('docs/assets/example.npy', 'fixture'),
                           ('vendor/code.py', 'print("must not execute")'), ('normal.py', 'original')]:
            path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text)
        (self.root / 'outside-link').symlink_to('/path/that/must/not/be/read')
        self.git('add', '.')
        self.git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'fixture')

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args])

    def test_committed_snapshot_and_review_candidates_are_separate_from_approval(self):
        (self.root / 'normal.py').write_text('dirty')
        (self.root / 'untracked.npy').write_text('untracked')
        inventory = scan_source(self.root)
        self.assertEqual(inventory['commit'], self.git('rev-parse', 'HEAD').decode().strip())
        self.assertEqual(inventory['file_count'], 6)
        self.assertNotIn('untracked.npy', [f['path'] for f in inventory['files']])
        self.assertEqual(next(f for f in inventory['files'] if f['path'] == 'normal.py')['object_id'],
                         self.git('rev-parse', 'HEAD:normal.py').decode().strip())
        kinds = {f['kind'] for f in inventory['findings']}
        self.assertTrue({'license_or_notice_candidate', 'external_material_candidate', 'data_or_image_candidate', 'symlink_review'} <= kinds)
        self.assertEqual(inventory['distribution_readiness'], 'not_assessed')
        self.assertTrue(all(f['review_state'] == 'needs_review' for f in inventory['findings']))
        draft = review_draft(inventory)
        result = validate(draft)
        self.assertEqual(result['open_requirements'], len(inventory['findings']) + 1)
        self.assertFalse(draft['distribution']['scope_confirmed'])

    def test_no_findings_does_not_approve_the_source(self):
        # A normal source file alone still needs scope confirmation.
        self.git('rm', '-rq', '.')
        (self.root / 'code.py').write_text('pass')
        self.git('add', '.')
        self.git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'source only')
        inventory = scan_source(self.root)
        self.assertEqual(inventory['findings'], [])
        self.assertEqual(validate(review_draft(inventory))['open_requirements'], 1)

    def test_html_and_markdown_escape_untrusted_paths(self):
        (self.root / '<img onerror=bad>.png').write_text('data')
        self.git('add', '.')
        self.git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'odd path')
        inventory = scan_source(self.root)
        # Add a literal file name to a finding to exercise all renderers.
        inventory['findings'][0]['path'] = '<script>bad</script>|[link](bad)'
        self.assertNotIn('<script>', render_source(inventory, 'html'))
        self.assertNotIn('[link](bad)', render_source(inventory, 'markdown'))

    def test_cli_modes_and_source_overwrite_protection(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(['--source-tree', str(self.root), '--format', 'json']), 0)
        self.assertEqual(json.loads(output.getvalue())['assessment'], 'source-inventory')
        for args in [['--source-ref', 'HEAD'], ['--source-tree', str(self.root), '--allow', 'MIT'],
                     ['--source-tree', str(self.root), '--output', str(self.root / 'LICENSE')],
                     ['--source-tree', str(self.root), '--source-ref=--help']]:
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(args), 2)
        self.assertEqual((self.root / 'LICENSE').read_text(), 'MIT')

    def test_bad_ref_subdirectory_and_nonrepository_are_errors(self):
        for root, ref in [(self.root, 'missing-ref'), (self.root / 'docs', 'HEAD')]:
            with self.assertRaises(ValueError):
                scan_source(root, ref)
        with tempfile.TemporaryDirectory() as outside:
            with self.assertRaises(ValueError):
                scan_source(Path(outside))

    def test_submodule_is_a_boundary_not_a_recursively_scanned_checkout(self):
        commit = self.git('rev-parse', 'HEAD').decode().strip()
        self.git('update-index', '--add', '--cacheinfo', '160000', commit, 'nested-submodule')
        self.git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'gitlink')
        inventory = scan_source(self.root)
        self.assertIn(('submodule_review', 'nested-submodule'), [(f['kind'], f['path']) for f in inventory['findings']])
        self.assertFalse(any(f['path'].startswith('nested-submodule/') for f in inventory['files']))

    def test_changed_source_and_removed_license_create_open_review_tasks(self):
        before = scan_source(self.root)
        baselines = tempfile.TemporaryDirectory()
        self.addCleanup(baselines.cleanup)
        baseline = Path(baselines.name) / 'baseline.json'
        baseline.write_text(render_source(before, 'json'))
        (self.root / 'LICENSE').unlink()
        (self.root / 'vendor/code.py').write_text('changed copied source')
        (self.root / 'docs/assets/new.png').write_text('new asset')
        self.git('add', '-A')
        self.git('update-index', '--chmod=+x', 'normal.py')
        self.git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'source changes')
        after = scan_source(self.root)
        changes = source_changes(load_source_baseline(baseline, self.root), after)
        by_path = {item['path']: item for item in changes}
        self.assertEqual(by_path['LICENSE']['change'], 'removed')
        self.assertEqual(by_path['docs/assets/new.png']['change'], 'added')
        self.assertEqual(by_path['vendor/code.py']['change'], 'changed')
        self.assertNotEqual(by_path['normal.py']['before']['mode'], by_path['normal.py']['after']['mode'])
        self.assertEqual(len(changes), 4)
        after.update(baseline_commit=before['commit'], changes=changes)
        draft = review_draft(after)
        self.assertTrue(all(item['state'] == 'needs_review' for item in draft['requirements']))
        self.assertEqual(validate(draft)['distribution_readiness'], 'not_assessed')
        self.assertEqual(sum(c['id'].startswith('change:') for c in draft['components']), len(changes))

    def test_same_source_remains_unreviewed_and_has_no_change_failure(self):
        inventory = scan_source(self.root)
        baseline = self.root / 'baseline.json'
        baseline.write_text(render_source(inventory, 'json'))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(['--source-tree', str(self.root), '--baseline', str(baseline),
                                   '--fail-on-change', '--format', 'json']), 0)
        report = json.loads(output.getvalue())
        self.assertEqual(report['changes'], [])
        self.assertEqual(report['distribution_readiness'], 'not_assessed')
        self.assertGreater(validate(report['review_draft'])['open_requirements'], 0)

    def test_baseline_must_match_real_git_objects_and_may_not_be_overwritten(self):
        inventory = scan_source(self.root)
        baseline = self.root / 'baseline.json'
        for invalid in [[], {'assessment':'source-inventory', 'commit':'HEAD'},
                        {**inventory, 'files':[]}, {**inventory, 'files_sha256':'0'*64},
                        {**inventory, 'tree':'0'*40}]:
            baseline.write_text(json.dumps(invalid))
            with self.subTest(invalid=type(invalid)), self.assertRaises(ValueError):
                load_source_baseline(baseline, self.root)
        baseline.write_text(render_source(inventory, 'json'))
        original = baseline.read_bytes()
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['--source-tree',str(self.root),'--baseline',str(baseline),'--output',str(baseline)]), 2)
            self.assertEqual(main(['--source-tree',str(self.root),'--fail-on-change']), 2)
        self.assertEqual(baseline.read_bytes(), original)

    def test_changed_source_exit_code_and_report_survive_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            baseline, report = Path(directory)/'baseline.json', Path(directory)/'changes.json'
            baseline.write_text(render_source(scan_source(self.root), 'json'))
            (self.root/'vendor/code.py').write_text('changed')
            self.git('add','vendor/code.py')
            self.git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','changed')
            args=['--source-tree',str(self.root),'--baseline',str(baseline),'--format','json','--output',str(report)]
            self.assertEqual(main(args),0)
            self.assertEqual(main([*args,'--fail-on-change']),1)
            data=json.loads(report.read_text())
            self.assertEqual(len(data['changes']),1)
            for format in ['html','markdown','csv','table']:
                rendered=render_source(data,format)
                self.assertIn('vendor/code.py',unescape(rendered))

    def test_symlink_target_and_submodule_revision_changes_are_not_followed(self):
        original = self.git('rev-parse', 'HEAD').decode().strip()
        self.git('update-index', '--add', '--cacheinfo', '160000', original, 'nested-submodule')
        self.git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'submodule baseline')
        before = scan_source(self.root)
        (self.root/'outside-link').unlink()
        (self.root/'outside-link').symlink_to('/another/nonexistent/target')
        self.git('add', 'outside-link')
        self.git('update-index', '--cacheinfo', '160000', before['commit'], 'nested-submodule')
        self.git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'reference changes')
        changes = source_changes(before, scan_source(self.root))
        self.assertEqual({item['path'] for item in changes}, {'outside-link','nested-submodule'})
        self.assertTrue(all(item['change']=='changed' for item in changes))
        self.assertTrue(all(item['before']['object_id'] != item['after']['object_id'] for item in changes))
