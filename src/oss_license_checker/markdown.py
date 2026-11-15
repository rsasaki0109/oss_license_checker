"""GitHub-compatible reports; metadata is rendered as literal table text."""

from collections import Counter
from html import escape
import json


def literal(value):
    text = str(value).replace('\r\n', '\n').replace('\r', '\n').replace('\t', ' ')
    return ''.join('<br>' if char == '\n' else f'&#{ord(char)};' if char in '\\`*_{}[]()#+-.!|~@'
                   else escape(char, quote=True) for char in text if char == '\n' or ord(char) >= 32)


def table(headers, rows):
    lines = ['| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join('---' for _ in headers) + ' |']
    lines.extend('| ' + ' | '.join(literal(value) for value in row) + ' |' for row in rows)
    return '\n'.join(lines) + '\n'


def render_markdown(rows, policy=None, scope=None, *, changes=None, fail_on_change=False):
    policy = policy or {}
    counts = Counter(row['status'] for row in rows)
    failed = bool(counts['denied'] or (policy.get('fail-unknown') and counts['unknown']))
    verdict = 'Policy check failed' if failed else 'Policy check passed'
    if not failed and fail_on_change and changes:
        verdict = 'Change check failed'
    parts = ['# OSS License Checker', f'**{verdict}**',
             'Scope: ' + literal(scope or 'Entire installed environment'),
             table(['Packages', 'Allowed', 'Denied', 'Unknown'],
                   [[len(rows), counts['allowed'], counts['denied'], counts['unknown']]]),
             '## Policy applied',
             table(['Setting', 'Value'], [
                 ['Allowed licenses', ', '.join(policy.get('allow', [])) or 'Unrestricted (no allow list)'],
                 ['Denied licenses', ', '.join(policy.get('deny', [])) or 'None specified'],
                 ['Unknown licenses', 'Fail the check' if policy.get('fail-unknown') else 'Report only']])]
    if changes is not None:
        parts += ['## Changes from baseline', f'{len(changes)} changes. ' +
                  ('Changes fail the check.' if fail_on_change else 'Changes are informational.'),
                  table(['Package', 'Change', 'Fields', 'Before', 'After'], [
                      [item['name'], item['change'], ', '.join(item['fields']),
                       json.dumps(item['before'], ensure_ascii=False), json.dumps(item['after'], ensure_ascii=False)]
                      for item in changes]) if changes else 'No package changes.']
    parts += ['## Package inventory', table(
        ['Package', 'Version', 'Metadata license', 'Effective license', 'Source', 'Status', 'Reason', 'Review evidence'],
        [[row['name'], row['version'], row['license'], row.get('effective_license', row['license']),
          row['source'], row['status'], row.get('reason', ''), row.get('override_reason', '')] for row in rows]
    ) if rows else 'No installed packages matched this scan.',
        'Allowed means compliance with the policy above, not a legal compatibility assessment. '
        'Current packages are re-evaluated against the current policy; unknown metadata requires review.']
    return '\n\n'.join(parts) + '\n'
