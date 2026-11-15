"""Compare inventories without trusting previous policy verdicts."""

import csv
import io
import json
import re
from packaging.utils import canonicalize_name

from .report import render_html
from .markdown import render_markdown


FIELDS = ("version", "license", "source", "status", "effective_license")


def index_inventory(rows):
    if not isinstance(rows, list):
        raise ValueError("Baseline packages must be a JSON array")
    result = {}
    for row in rows:
        if isinstance(row, dict):
            row = {"effective_license": row.get("license"), **row}
        if not isinstance(row, dict) or any(not isinstance(row.get(key), str) for key in ("name", *FIELDS)):
            raise ValueError("Baseline rows require string name, version, license, source and status")
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?", row["name"]):
            raise ValueError(f"Invalid baseline package name: {row['name']!r}")
        if row["status"] not in {"allowed", "denied", "unknown"}:
            raise ValueError(f"Invalid baseline status for {row['name']}")
        name = canonicalize_name(row["name"])
        if name in result:
            raise ValueError(f"Duplicate baseline package: {name}")
        result[name] = {key: row[key] for key in ("name", *FIELDS)}
    return result


def load_baseline(path):
    document = json.loads(path.read_text(encoding="utf-8"))
    # Both inventory JSON and the output of a prior comparison can be baselines.
    if isinstance(document, dict):
        document = document.get("packages")
    index_inventory(document)
    return document


def compare(before, after):
    previous, current = index_inventory(before), index_inventory(after)
    changes = []
    for name in sorted(previous.keys() | current.keys()):
        old, new = previous.get(name), current.get(name)
        fields = [key for key in FIELDS if old is not None and new is not None and old[key] != new[key]]
        if old is None or new is None or fields:
            changes.append({"name": name, "change": "added" if old is None else "removed" if new is None else "changed",
                            "fields": fields, "before": old, "after": new})
    return changes


def render_comparison(rows, changes, format, *, policy, scope, fail_on_change):
    if format == "markdown":
        return render_markdown(rows, policy, scope, changes=changes, fail_on_change=fail_on_change)
    if format == "json":
        return json.dumps({"packages": rows, "changes": changes}, ensure_ascii=False, indent=2) + "\n"
    if format == "html":
        return render_html(rows, policy, scope, changes=changes, fail_on_change=fail_on_change)
    if format == "csv":
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=["name", "change", "fields", "before", "after"])
        writer.writeheader()
        for change in changes:
            writer.writerow({**change, "fields": ", ".join(change["fields"]),
                             "before": json.dumps(change["before"], ensure_ascii=False),
                             "after": json.dumps(change["after"], ensure_ascii=False)})
        return stream.getvalue()
    lines = [f"Baseline comparison: {len(changes)} package changes", "NAME\tCHANGE\tFIELDS\tBEFORE\tAFTER"]
    for change in changes:
        lines.append("\t".join([change["name"], change["change"], ", ".join(change["fields"]),
                                 json.dumps(change["before"], ensure_ascii=False),
                                 json.dumps(change["after"], ensure_ascii=False)]))
    return "\n".join(lines) + "\n"
