"""Self-contained HTML reports with no scripts or remote resources."""

from collections import Counter
from html import escape
import json


STYLE = """
:root{color-scheme:light;--ink:#172c2b;--muted:#596c69;--line:#d8e3df}
*{box-sizing:border-box}body{margin:0;background:#f3f6f3;color:var(--ink);
font:16px/1.6 system-ui,-apple-system,sans-serif}main{max-width:1180px;margin:auto;padding:48px 28px}
header{background:#102c29;color:#eff9f1;border-radius:22px;padding:40px;position:relative}
.eyebrow{font-size:12px;letter-spacing:.16em;font-weight:700;text-transform:uppercase;color:#a8d6bb}
h1{font-size:clamp(32px,5vw,52px);line-height:1.1;letter-spacing:-.04em;margin:20px 0}
header p{color:#c4d8ce;margin:8px 0;overflow-wrap:anywhere}.verdict{display:inline-block;background:#29483d;
padding:8px 14px;border-radius:8px;font-weight:700;margin:16px 0 0}
.verdict.failed{background:#643a2b;color:#ffdbc4}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin:24px 0}
.card{background:white;border:1px solid var(--line);border-radius:14px;padding:22px}
.card strong{display:block;font-size:34px;line-height:1.2}.card span{color:var(--muted);font-size:14px}
h2{font-size:22px;margin:32px 0 12px;letter-spacing:-.02em}.panel{background:white;
border:1px solid var(--line);border-radius:14px;padding:24px}.policy{margin:0;display:grid;grid-template-columns:150px 1fr;gap:12px}
dt{font-weight:700}dd{margin:0;overflow-wrap:anywhere}code{font:14px/1.6 ui-monospace,monospace}
.table-wrap{overflow-x:auto;background:white;border:1px solid var(--line);border-radius:14px}
table{width:100%;border-collapse:collapse;text-align:left;font-size:14px}caption{text-align:left;padding:20px 22px;color:var(--muted)}
th{font-size:12px;text-transform:uppercase;letter-spacing:.05em;background:#eaf0ec;color:#425c55}
th,td{padding:16px 22px;border-bottom:1px solid var(--line);vertical-align:top}
tbody tr:last-child td{border-bottom:0}.license{min-width:220px;max-width:420px;white-space:pre-wrap;overflow-wrap:anywhere}
.badge{display:inline-block;padding:3px 10px;border-radius:6px;font-size:12px;font-weight:700;white-space:nowrap}
.allowed{color:#18543c;background:#def2e4}.denied{color:#873020;background:#ffe4d7}
.unknown{color:#74520c;background:#fff0bd}.muted,footer{color:var(--muted)}footer{font-size:13px;margin:28px 0}
@media(max-width:650px){main{padding:20px 14px}header{padding:26px}.cards{grid-template-columns:repeat(2,1fr);gap:10px}
.card{padding:16px}.policy{grid-template-columns:1fr;gap:4px}dd{margin-bottom:12px}}
@media print{body{background:white}main{padding:0}header{print-color-adjust:exact}.cards{break-inside:avoid}}
"""


def render_html(rows, policy=None, scope=None, *, changes=None, fail_on_change=False):
    policy = policy or {}
    allow, deny = policy.get("allow", []), policy.get("deny", [])
    fail_unknown = policy.get("fail-unknown", False)
    counts = Counter(row["status"] for row in rows)
    failed = bool(counts["denied"] or (fail_unknown and counts["unknown"]))
    esc = lambda value: escape(str(value), quote=True)
    cards = "".join(
        f'<div class="card"><strong>{count}</strong><span>{label}</span></div>'
        for count, label in [(len(rows), "Packages inspected"), (counts["allowed"], "Allowed"),
                             (counts["denied"], "Denied"), (counts["unknown"], "Unknown")]
    )
    body = "".join(
        '<tr>' + ''.join(f'<td>{esc(row[key])}</td>' for key in ("name", "version"))
        + f'<td class="license"><code>{esc(row["license"])}</code></td>'
        + f'<td class="license"><code>{esc(row.get("effective_license", row["license"]))}</code></td>'
        + f'<td class="muted">{esc(row["source"])}</td>'
        + f'<td><span class="badge {row["status"] if row["status"] in {"allowed", "denied", "unknown"} else "unknown"}">{esc(row["status"])}</span></td>'
        + f'<td>{esc(row.get("reason", ""))}'
        + (f'<p><strong>Reviewed override:</strong> {esc(row["override_reason"])}</p>' if row.get("override_reason") else '') + '</td></tr>'
        for row in rows
    )
    if not rows:
        body = '<tr><td colspan="7">No installed packages matched this scan.</td></tr>'
    verdict = "Policy check failed" if failed else "Policy check passed"
    comparison = ""
    if changes is not None:
        if fail_on_change and changes and not failed:
            verdict = "Change check failed"
        failed = failed or bool(fail_on_change and changes)
        change_rows = "".join(
            f'<tr><td>{esc(change["name"])}</td><td>{esc(change["change"])}</td>'
            f'<td>{esc(", ".join(change["fields"]))}</td>'
            f'<td class="license"><code>{esc(json.dumps(change["before"], ensure_ascii=False, indent=2))}</code></td>'
            f'<td class="license"><code>{esc(json.dumps(change["after"], ensure_ascii=False, indent=2))}</code></td></tr>'
            for change in changes
        ) or '<tr><td colspan="5">No package changes.</td></tr>'
        comparison = f'''<h2>Changes from baseline</h2><div class="table-wrap"><table>
<caption>{len(changes)} package changes · {'Changes fail the check' if fail_on_change else 'Changes are informational'}.
Current packages are always re-evaluated against the current policy.</caption>
<thead><tr><th scope="col">Package</th><th scope="col">Change</th><th scope="col">Fields</th>
<th scope="col">Before</th><th scope="col">After</th></tr></thead><tbody>{change_rows}</tbody></table></div>'''
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>License report — OSS License Checker</title><style>{STYLE}</style></head>
<body><main><header><div class="eyebrow">OSS License Checker / dependency inventory</div>
<h1>Know what ships.</h1><p>License evidence and policy results for your Python dependencies.</p>
<p>Scope: {esc(scope or 'Entire installed environment')}</p>
<div class="verdict{' failed' if failed else ''}">{verdict}</div></header>
<section aria-label="Summary" class="cards">{cards}</section>
<h2>Policy applied</h2><section class="panel" aria-label="Effective policy"><dl class="policy">
<dt>Allowed licenses</dt><dd><code>{esc(', '.join(allow) if allow else 'Unrestricted (no allow list)')}</code></dd>
<dt>Denied licenses</dt><dd><code>{esc(', '.join(deny) if deny else 'None specified')}</code></dd>
<dt>Unknown licenses</dt><dd>{'Fail the check' if fail_unknown else 'Report for review; do not fail the check'}</dd>
</dl></section>{comparison}<h2>Package inventory</h2><div class="table-wrap"><table>
<caption>{len(rows)} packages · Metadata evidence is preserved below.</caption>
<thead><tr><th scope="col">Package</th><th scope="col">Version</th><th scope="col">Metadata license</th><th scope="col">Effective license</th>
<th scope="col">Metadata source</th><th scope="col">Status</th><th scope="col">Reason</th></tr></thead><tbody>{body}</tbody>
</table></div><footer>Allowed means compliance with the policy above, not a legal compatibility assessment.
Unknown metadata requires review of the distribution's LICENSE and NOTICE files.
OR expressions pass when at least one alternative is permitted.
This report is self-contained and works offline.</footer></main></body></html>
'''
