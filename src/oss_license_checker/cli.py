"""Read local package metadata without executing package code or accessing the network."""

import argparse
import csv
import io
import json
import re
import sys
from importlib import metadata
from pathlib import Path
from packaging.licenses import canonicalize_license_expression
from packaging.version import Version

from .project import dependency_names, load_policy
from .report import render_html
from .baseline import compare, load_baseline, render_comparison
from .overrides import validate_overrides
from .bundle import create_bundle
from .markdown import render_markdown
from .output import validate_output_paths, write_report
from .environment import installed_distributions
from .source import scan_source, render_source, load_source_baseline, source_changes


def normalize(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def license_info(meta):
    expression = (meta.get("License-Expression") or "").strip()
    if expression:
        return expression, "License-Expression"
    # Older metadata is not reliably SPDX. Retain it as evidence, never guess.
    value = (meta.get("License") or "").strip()
    if value and value.upper() not in {"UNKNOWN", "UNLICENSED"}:
        return value, "License"
    classifiers = meta.get_all("Classifier") or []
    values = [x for x in classifiers if x.startswith("License ::")]
    return ("; ".join(values), "Classifier") if values else ("UNKNOWN", "missing")


def normalize_rules(rules):
    """Policy entries name one license, optionally qualified by one exception."""
    normalized = []
    for rule in rules:
        try:
            value = canonicalize_license_expression(rule)
        except ValueError as exc:
            raise ValueError(f"Invalid policy entry {rule!r}: {exc}") from exc
        tokens = value.split()
        if not (len(tokens) == 1 or (len(tokens) == 3 and tokens[1] == "WITH")) or any(
            token in {"AND", "OR", "(", ")"} or "(" in token or ")" in token for token in tokens
        ):
            raise ValueError(f"Policy entry must name one license or license WITH exception: {rule!r}")
        normalized.append(value)
    return normalized


def evaluate(expression, allow, deny):
    """Validate SPDX identifiers before evaluating policy alternatives."""
    expression = canonicalize_license_expression(expression)
    allow, deny = set(normalize_rules(allow)), set(normalize_rules(deny))
    tokens = re.findall(r"\(|\)|[^\s()]+", expression)
    position = 0

    def atom():
        nonlocal position
        if position >= len(tokens):
            raise ValueError("incomplete expression")
        token = tokens[position]
        position += 1
        if token == "(":
            value = either()
            if position >= len(tokens) or tokens[position] != ")":
                raise ValueError("unclosed parenthesis")
            position += 1
            return value
        if token in {"AND", "OR", "WITH", ")"} or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.+-]*", token):
            raise ValueError("unsupported license syntax")
        if position < len(tokens) and tokens[position] == "WITH":
            position += 1
            if position >= len(tokens) or tokens[position] in {"AND", "OR", "WITH"} or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.+-]*", tokens[position]):
                raise ValueError("missing exception")
            token += " WITH " + tokens[position]
            position += 1
        base = token.split(" WITH ")[0]
        if base.startswith("LicenseRef-") and token not in allow and token not in deny and base not in deny:
            raise ValueError(f"Custom license requires an explicit policy entry: {base}")
        return token not in deny and base not in deny and (not allow or token in allow)

    def both():
        nonlocal position
        value = atom()
        while position < len(tokens) and tokens[position] == "AND":
            position += 1
            right = atom()
            value = value and right
        return value

    def either():
        nonlocal position
        value = both()
        while position < len(tokens) and tokens[position] == "OR":
            position += 1
            right = both()
            value = value or right
        return value

    result = either()
    if position != len(tokens):
        raise ValueError("unsupported license syntax")
    return result


def collect(names=None, allow=(), deny=(), fail_unknown=False, recursive=False, overrides=None):
    allow, deny = normalize_rules(allow), normalize_rules(deny)
    overrides = validate_overrides(overrides if overrides is not None else {})
    installed = installed_distributions(metadata.distributions())
    selected = dependency_names(installed, names) if recursive else sorted({normalize(n) for n in names} if names else installed)
    rows = []
    for name in selected:
        if name not in installed:
            raise ValueError(f"Package is not installed: {name}")
        dist = installed[name]
        license_value, source = license_info(dist.metadata)
        override = overrides.get(name)
        if override and Version(dist.version) != Version(override["version"]):
            raise ValueError(f"Override for {name} was reviewed for {override['version']}, but installed version is {dist.version}; review the license again")
        effective_license = override["license"] if override else license_value
        status = "unknown"
        reason = "License metadata is missing"
        # Classifier labels and free-form license bodies need manual review.
        if override or (source != "missing" and source != "Classifier"):
            try:
                if effective_license.upper() in {"UNKNOWN", "UNLICENSED", "NONE", "NOASSERTION"}:
                    raise ValueError("unknown license")
                status = "allowed" if evaluate(effective_license, set(allow), set(deny)) else "denied"
                if status == "allowed":
                    reason = "A license alternative is permitted" if allow or deny else "SPDX expression recognized; no allow/deny policy evaluated"
                else:
                    reason = "No license alternative is permitted by the policy"
            except ValueError as exc:
                reason = str(exc)
        elif source == "Classifier":
            reason = "Classifier labels require manual review"
        rows.append({"name": dist.metadata["Name"], "version": dist.version,
                     "license": license_value, "source": source, "status": status, "reason": reason,
                     "effective_license": effective_license, "override_reason": override["reason"] if override else "",
                     "assessment": "policy-evaluated" if allow or deny else "inventory-only"})
    failed = any(r["status"] == "denied" or (fail_unknown and r["status"] == "unknown") for r in rows)
    return rows, failed


def render(rows, format, *, policy=None, scope=None):
    if format == "markdown":
        return render_markdown(rows, policy, scope)
    if format == "html":
        return render_html(rows, policy, scope)
    if format == "json":
        return json.dumps(rows, ensure_ascii=False, indent=2) + "\n"
    if format == "csv":
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=["name", "version", "license", "source", "status", "reason", "effective_license", "override_reason", "assessment"])
        writer.writeheader()
        writer.writerows(rows)
        return stream.getvalue()
    return "\n".join(["NAME\tVERSION\tLICENSE\tSTATUS\tREASON\tEFFECTIVE_LICENSE\tOVERRIDE_REASON\tASSESSMENT"] + [
        "\t".join(str(r.get(k, "")).replace("\n", " ").replace("\r", " ").replace("\t", " ")
                  for k in ("name", "version", "license", "status", "reason", "effective_license", "override_reason", "assessment")) for r in rows]) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    try:
        installed_version = metadata.version("oss-license-checker")
    except metadata.PackageNotFoundError:
        installed_version = "unknown (not installed)"
    parser.add_argument("--version", action="version", version=f"oss-license-checker {installed_version}")
    parser.add_argument("packages", nargs="*", help="Installed package names (default: entire environment)")
    parser.add_argument("--format", choices=["table", "json", "csv", "html", "markdown"], default="table")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--source-tree", type=Path, help="Inventory a Git repository's committed source tree for publication review")
    parser.add_argument("--source-ref", help="Commit or ref to inspect with --source-tree (default: HEAD)")
    parser.add_argument("--license-bundle", type=Path, help="Collect installed LICENSE/NOTICE evidence and manifest into a ZIP")
    parser.add_argument("--fail-missing-license-files", action="store_true", help="Fail on missing evidence; requires --license-bundle")
    parser.add_argument("--baseline", type=Path, help="Compare with a previous JSON inventory")
    parser.add_argument("--fail-on-change", action="store_true", help="Fail on any inventory change; requires --baseline")
    parser.add_argument("--recursive", action="store_true", help="Include installed transitive dependencies; supports root[extra]")
    parser.add_argument("--config", type=Path, help="Policy TOML or pyproject.toml (explicit opt-in)")
    parser.add_argument("--allow", action="append", default=None, help="Allowed SPDX identifier; repeatable; replaces config allow list")
    parser.add_argument("--deny", action="append", default=None, help="Denied SPDX identifier; repeatable; replaces config deny list")
    parser.add_argument("--fail-unknown", action=argparse.BooleanOptionalAction, default=None)
    args = parser.parse_args(argv)
    try:
        if args.source_ref is not None and not args.source_tree:
            raise ValueError('--source-ref requires --source-tree')
        if args.source_tree:
            if any([args.packages, args.recursive, args.config, args.license_bundle,
                    args.allow is not None, args.deny is not None, args.fail_unknown is not None,
                    args.fail_missing_license_files]):
                raise ValueError('Source inventory cannot be combined with installed-package policy, dependency or bundle options')
            if args.fail_on_change and not args.baseline:
                raise ValueError('--fail-on-change requires --baseline')
            validate_output_paths(report=args.output, baseline=args.baseline)
            baseline = load_source_baseline(args.baseline, args.source_tree) if args.baseline else None
            inventory = scan_source(args.source_tree, args.source_ref or 'HEAD')
            if baseline is not None:
                inventory['baseline_commit'] = baseline['commit']
                inventory['changes'] = source_changes(baseline, inventory)
            if args.output:
                try:
                    relative_output = args.output.resolve().relative_to(args.source_tree.resolve()).as_posix()
                except ValueError:
                    relative_output = None
                if relative_output in {entry['path'] for entry in inventory['files']}:
                    raise ValueError('Source report must not overwrite a tracked file in the inspected tree')
                write_report(args.output, render_source(inventory, args.format))
            else:
                sys.stdout.write(render_source(inventory, args.format))
            return 1 if args.fail_on_change and inventory.get('changes') else 0
        if args.fail_missing_license_files and not args.license_bundle:
            raise ValueError("--fail-missing-license-files requires --license-bundle")
        validate_output_paths(args.output, args.license_bundle, args.config, args.baseline)
        if args.fail_on_change and not args.baseline:
            raise ValueError("--fail-on-change requires --baseline")
        baseline = load_baseline(args.baseline) if args.baseline else None
        policy = load_policy(args.config) if args.config else {}
        allow = args.allow if args.allow is not None else policy.get("allow", [])
        deny = args.deny if args.deny is not None else policy.get("deny", [])
        allow, deny = normalize_rules(allow), normalize_rules(deny)
        fail_unknown = args.fail_unknown if args.fail_unknown is not None else policy.get("fail-unknown", False)
        rows, failed = collect(args.packages, allow, deny, fail_unknown, args.recursive, policy.get("overrides", {}))
        scope = None
        if args.packages:
            scope = ", ".join(args.packages) + (" (including transitive dependencies)" if args.recursive else " (selected packages only)")
        effective_policy = {"allow": allow, "deny": deny, "fail-unknown": fail_unknown}
        if baseline is not None:
            changes = compare(baseline, rows)
            output = render_comparison(rows, changes, args.format, policy=effective_policy,
                                       scope=scope, fail_on_change=args.fail_on_change)
            failed = failed or (args.fail_on_change and bool(changes))
        else:
            output = render(rows, args.format, policy=effective_policy, scope=scope)
        missing_evidence = create_bundle(rows, args.license_bundle) if args.license_bundle else False
        if missing_evidence:
            print("License evidence is missing for some packages; see manifest.json in the license bundle", file=sys.stderr)
        if args.output:
            write_report(args.output, output)
        else:
            sys.stdout.write(output)
        return 1 if failed or (args.fail_missing_license_files and missing_evidence) else 0
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
