"""Relate historical review records to a verified source comparison."""

import json


def compare_review(path, baseline, current, changes):
    record = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(record, dict) or record.get('format') != 'distribution-review-draft':
        raise ValueError('Expected a source publication review record')
    distribution = record.get('distribution')
    if (not isinstance(distribution, dict) or distribution.get('kind') != 'source'
            or distribution.get('id') != 'source-' + baseline['commit']):
        raise ValueError('Review record must match the source baseline commit')
    evidence = index_records(record, 'evidence')
    source = evidence.get('source-tree', {})
    if source.get('kind') != 'source_reference' or source.get('location') != 'git-tree:' + baseline['tree']:
        raise ValueError('Review record must reference the source baseline tree')

    components = index_records(record, 'components')
    requirements = index_records(record, 'requirements')
    candidates = {finding['id']: finding['path'] for finding in baseline['findings']}
    current_candidates = {finding['id'] for finding in current['findings']}
    changed_paths = {change['path'] for change in changes}
    affected_paths = set(changed_paths)
    for changed in changed_paths:
        parts = changed.split('/')
        affected_paths.update('/'.join(parts[:i]) for i in range(1, len(parts)))
    tree_changed = baseline['tree'] != current['tree']
    items = []
    for item_id, item in requirements.items():
        state = item.get('state')
        component = item.get('component_ref')
        if (not isinstance(state, str) or state not in {'needs_review', 'todo', 'done', 'not_applicable', 'blocked'}
                or not isinstance(component, str) or component not in components):
            raise ValueError(f'Invalid state or component reference in prior requirement {item_id!r}')
        candidate = candidates.get(component)
        directly_affected = False
        if candidate is not None:
            parts = candidate.split('/')
            ancestors = ('/'.join(parts[:i]) for i in range(1, len(parts)))
            directly_affected = (component not in current_candidates or candidate in affected_paths
                                 or (candidate == '.' and bool(changed_paths))
                                 or any(parent in changed_paths for parent in ancestors))
        if state in {'done', 'not_applicable'} and (tree_changed or directly_affected):
            follow_up = 'recheck'
        elif state in {'done', 'not_applicable'}:
            follow_up = 'historical'
        else:
            follow_up = 'open'
        items.append({'id': item_id, 'component': candidate or component,
                      'previous_state': state, 'follow_up': follow_up,
                      'candidate_changed': directly_affected})
    return items


def index_records(record, field):
    items = record.get(field)
    if not isinstance(items, list):
        raise ValueError(f'Review record requires a {field} array')
    indexed = {}
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get('id'), str) or not item['id']:
            raise ValueError(f'Invalid ID in review record {field}')
        if item['id'] in indexed:
            raise ValueError(f'Duplicate ID in review record {field}: {item["id"]!r}')
        indexed[item['id']] = item
    return indexed
