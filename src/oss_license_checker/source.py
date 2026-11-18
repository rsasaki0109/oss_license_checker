"""Inventory an immutable Git source tree without reading working-tree files."""

import csv
import hashlib
from html import escape
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess

from .markdown import table
from .report import STYLE


def git(repository, *arguments):
    env = {**os.environ, 'GIT_NO_LAZY_FETCH': '1', 'GIT_NO_REPLACE_OBJECTS': '1', 'GIT_OPTIONAL_LOCKS': '0'}
    result = subprocess.run(['git', '-C', str(repository), *arguments], capture_output=True, env=env)
    if result.returncode:
        raise ValueError('Git source inventory failed: ' + result.stderr.decode('utf-8', errors='replace').strip())
    return result.stdout


def scan_source(repository, ref='HEAD'):
    root = git(repository, 'rev-parse', '--show-toplevel').decode().strip()
    if repository.resolve() != Path(root).resolve():
        raise ValueError('--source-tree must point to the repository root')
    commit = git(repository, 'rev-parse', '--verify', '--end-of-options', ref + '^{commit}').decode().strip()
    tree = git(repository, 'rev-parse', commit + '^{tree}').decode().strip()
    entries = git(repository, 'ls-tree', '-r', '-z', '--full-tree', commit)
    files, groups = [], {}

    def candidate(kind, path):
        groups[(kind, path)] = groups.get((kind, path), 0) + 1

    for entry in entries.split(b'\0'):
        if not entry:
            continue
        header, raw_path = entry.split(b'\t', 1)
        mode, object_type, object_id = header.decode('ascii').split()
        path = raw_path.decode('utf-8')
        files.append({'path': path, 'mode': mode, 'object_type': object_type, 'object_id': object_id})
        parts = PurePosixPath(path).parts
        if mode == '160000':
            candidate('submodule_review', path)
            continue
        if mode == '120000':
            candidate('symlink_review', path)
            continue
        if re.fullmatch(r'(?:licen[cs]e|copying|notice|copyright)(?:[._-].*)?', parts[-1], re.I):
            candidate('license_or_notice_candidate', path)
        for index, part in enumerate(parts[:-1]):
            if part.lower() in {'vendor', 'vendored', 'third_party', 'third-party', 'external'}:
                candidate('external_material_candidate', '/'.join(parts[:index + 1]))
                break
        if PurePosixPath(path).suffix.lower() in {'.png', '.jpg', '.jpeg', '.gif', '.npy', '.npz', '.bin', '.pcd', '.bag', '.mcap'}:
            marker = next((i for i, part in enumerate(parts[:-1]) if part.lower() in {'assets', 'resources', 'data', 'datasets', 'fixtures'}), None)
            group = '/'.join(parts[:marker + 1]) if marker is not None else str(PurePosixPath(path).parent)
            candidate('data_or_image_candidate', group)
        if re.search(r'\.(?:so(?:\.\d+)*|dll|dylib|whl|a|lib)$', path, re.I):
            candidate('binary_candidate', path)
    findings = [{'id': kind + ':' + hashlib.sha256(path.encode()).hexdigest(), 'kind': kind, 'path': path,
                 'file_count': count, 'review_state': 'needs_review'} for (kind, path), count in sorted(groups.items())]
    manifest_hash = hashlib.sha256(json.dumps(files, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {'assessment': 'source-inventory', 'distribution_readiness': 'not_assessed', 'commit': commit, 'tree': tree,
            'files_sha256': manifest_hash, 'file_count': len(files), 'files': files, 'findings': findings,
            'coverage': 'Entire tracked Git tree at the resolved commit; working-tree edits and untracked files excluded',
            'limits': 'Path-based review candidates only. No license identification or obligations inference; copied or renamed material may be missed. Symlink targets and submodule contents are not followed.'}


def review_draft(inventory):
    evidence = {'id': 'source-tree', 'kind': 'source_reference', 'location': 'git-tree:' + inventory['tree'],
                'sha256': None, 'artifact_sha256': None,
                'description': 'Source manifest SHA-256 ' + inventory['files_sha256'] + '; path inventory, not fulfillment evidence'}
    component = {'id': 'source-scope', 'name': 'Tracked source tree', 'revision': inventory['commit'], 'kind': 'source_code',
                 'inclusion': 'unknown', 'inclusion_basis': 'Snapshot inspected; final publication scope requires confirmation',
                 'review_state': 'needs_review', 'license_expression': None, 'evidence_refs': ['source-tree']}

    def requirement(id, component_id, description, kind='license_review'):
        return {'id': id, 'component_ref': component_id, 'kind': kind, 'description': description,
                'basis': 'Observed tracked paths require review of origin, applicable terms and intended publication scope',
                'state': 'needs_review', 'reason': 'No applicability or fulfillment decision has been made',
                'evidence_refs': ['source-tree'], 'reviewed_by': None, 'reviewed_at': None}

    components = [component]
    requirements = [requirement('confirm-scope', 'source-scope', 'Confirm the published paths and review coverage', 'scope_review')]
    for finding in inventory['findings']:
        components.append({**component, 'id': finding['id'], 'name': finding['path'],
                           'kind': 'data' if finding['kind'] == 'data_or_image_candidate' else 'source_code'})
        requirements.append(requirement('review:' + finding['id'], finding['id'],
                                        'Review candidate ' + finding['path'] + ' (' + finding['kind'] + '); determine origin, applicable terms and required actions'))
    evidence_records = [evidence]
    if 'baseline_commit' in inventory:
        evidence_records.append({'id': 'source-baseline', 'kind': 'source_reference',
                                 'location': 'git-commit:' + inventory['baseline_commit'], 'sha256': None,
                                 'artifact_sha256': None, 'description': 'Previous source tree verified against local Git objects'})
    for change in inventory.get('changes', []):
        id = 'change:' + hashlib.sha256(change['path'].encode()).hexdigest()
        components.append({**component, 'id': id, 'name': change['path'],
                           'evidence_refs': ['source-tree', 'source-baseline']})
        task = requirement('review:' + id, id, 'Review ' + change['change'] + ' tracked path ' + change['path'])
        task['evidence_refs'] = ['source-tree', 'source-baseline']
        task['basis'] = 'Git entry change: ' + json.dumps({'before': change['before'], 'after': change['after']}, ensure_ascii=False)
        requirements.append(task)
    return {'format': 'distribution-review-draft',
            'distribution': {'id': 'source-' + inventory['commit'], 'description': 'Source publication review at a fixed commit; final scope unconfirmed',
                             'kind': 'source', 'scope_confirmed': False, 'artifact_sha256': None},
            'components': components, 'requirements': requirements, 'evidence': evidence_records}


def load_source_baseline(path, repository):
    document = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(document, dict) or document.get('assessment') != 'source-inventory':
        raise ValueError('Source baseline must be a source-inventory JSON report')
    commit = document.get('commit')
    if not isinstance(commit, str) or not re.fullmatch(r'(?:[a-f0-9]{40}|[a-f0-9]{64})', commit):
        raise ValueError('Source baseline requires an immutable Git commit ID')
    verified = scan_source(repository, commit)
    for key in ['tree', 'files', 'files_sha256', 'file_count']:
        if document.get(key) != verified[key] or type(document.get(key)) is not type(verified[key]):
            raise ValueError(f'Source baseline {key} does not match the referenced Git commit')
    return verified


def source_changes(before, after):
    previous = {entry['path']: entry for entry in before['files']}
    current = {entry['path']: entry for entry in after['files']}
    changes = []
    for path in sorted(previous.keys() | current.keys()):
        old, new = previous.get(path), current.get(path)
        if old != new:
            changes.append({'path': path, 'change': 'added' if old is None else 'removed' if new is None else 'changed',
                            'before': old, 'after': new, 'review_state': 'needs_review'})
    return changes


def render_source(inventory, format):
    if format == 'json':
        return json.dumps({**inventory, 'review_draft': review_draft(inventory)}, ensure_ascii=False, indent=2) + '\n'
    fields = ['kind', 'path', 'file_count', 'review_state']
    rows = [[finding[field] for field in fields] for finding in inventory['findings']]
    summary = f"Source inventory: {inventory['file_count']} tracked entries. Commit: {inventory['commit']}. Distribution readiness: not assessed."
    if 'changes' in inventory:
        summary += f" Baseline: {inventory['baseline_commit']}. Changed entries: {len(inventory['changes'])}."
        # Non-JSON comparisons retain current candidates alongside the change rows.
        fields = ['kind_or_change', 'path', 'file_count', 'review_state']
        rows = [[change['change'], change['path'], 1, change['review_state']] for change in inventory['changes']] + rows
    if format == 'csv':
        stream = io.StringIO(newline='')
        writer = csv.writer(stream); writer.writerow(fields); writer.writerows(rows)
        return stream.getvalue()
    if format == 'markdown':
        return '# Source publication review\n\n' + summary + '\n\n' + inventory['coverage'] + '\n\n' + inventory['limits'] + '\n\n' + table(fields, rows)
    if format == 'html':
        cells = ''.join('<tr>' + ''.join('<td>' + escape(str(value)) + '</td>' for value in row) + '</tr>' for row in rows)
        headings = ''.join('<th scope="col">' + field + '</th>' for field in fields)
        return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>Source publication review</title><style>{STYLE}</style></head>
<body><main><h1>Source publication review</h1><p>{escape(summary)}</p>
<p>{escape(inventory['coverage'])}</p><p>{escape(inventory['limits'])}</p>
<div class="table-wrap"><table><thead><tr>{headings}</tr></thead><tbody>{cells}</tbody></table></div>
</main></body></html>\n'''
    lines = ['\t'.join(str(value).replace('\r', '\\r').replace('\n', '\\n').replace('\t', '\\t') for value in row) for row in rows]
    return '\n'.join([summary, inventory['coverage'], inventory['limits'], '\t'.join(fields), *lines]) + '\n'
