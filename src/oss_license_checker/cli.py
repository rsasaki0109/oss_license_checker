"""Read local package metadata without executing package code or accessing the network."""

import argparse
import csv
import io
import json
import re
import sys
from importlib import metadata
from pathlib import Path

from .project import dependency_names, load_policy
from .report import render_html


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


def evaluate(expression, allow, deny):
    """Evaluate a small, explicit SPDX grammar. Unsupported syntax fails closed."""
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


def collect(names=None, allow=(), deny=(), fail_unknown=False, recursive=False):
    installed = {normalize(d.metadata["Name"]): d for d in metadata.distributions() if d.metadata["Name"]}
    selected = dependency_names(installed, names) if recursive else sorted({normalize(n) for n in names} if names else installed)
    rows = []
    for name in selected:
        if name not in installed:
            raise ValueError(f"Package is not installed: {name}")
        dist = installed[name]
        license_value, source = license_info(dist.metadata)
        status = "unknown"
        # Classifier labels and free-form license bodies need manual review.
        if source != "missing" and source != "Classifier":
            try:
                if license_value.upper() in {"UNKNOWN", "UNLICENSED", "NONE", "NOASSERTION"}:
                    raise ValueError("unknown license")
                if source == "License" and license_value not in set(allow) | set(deny):
                    raise ValueError("unverified legacy license")
                status = "allowed" if evaluate(license_value, set(allow), set(deny)) else "denied"
            except ValueError:
                pass
        rows.append({"name": dist.metadata["Name"], "version": dist.version,
                     "license": license_value, "source": source, "status": status})
    failed = any(r["status"] == "denied" or (fail_unknown and r["status"] == "unknown") for r in rows)
    return rows, failed


def render(rows, format, *, policy=None, scope=None):
    if format == "html":
        return render_html(rows, policy, scope)
    if format == "json":
        return json.dumps(rows, ensure_ascii=False, indent=2) + "\n"
    if format == "csv":
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=["name", "version", "license", "source", "status"])
        writer.writeheader()
        writer.writerows(rows)
        return stream.getvalue()
    return "\n".join(["NAME\tVERSION\tLICENSE\tSTATUS"] + [
        "\t".join(str(r[k]).replace("\n", " ").replace("\r", " ").replace("\t", " ")
                  for k in ("name", "version", "license", "status")) for r in rows]) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packages", nargs="*", help="Installed package names (default: entire environment)")
    parser.add_argument("--format", choices=["table", "json", "csv", "html"], default="table")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--recursive", action="store_true", help="Include installed transitive dependencies; supports root[extra]")
    parser.add_argument("--config", type=Path, help="Policy TOML or pyproject.toml (explicit opt-in)")
    parser.add_argument("--allow", action="append", default=None, help="Allowed SPDX identifier; repeatable; replaces config allow list")
    parser.add_argument("--deny", action="append", default=None, help="Denied SPDX identifier; repeatable; replaces config deny list")
    parser.add_argument("--fail-unknown", action=argparse.BooleanOptionalAction, default=None)
    args = parser.parse_args(argv)
    try:
        policy = load_policy(args.config) if args.config else {}
        allow = args.allow if args.allow is not None else policy.get("allow", [])
        deny = args.deny if args.deny is not None else policy.get("deny", [])
        fail_unknown = args.fail_unknown if args.fail_unknown is not None else policy.get("fail-unknown", False)
        rows, failed = collect(args.packages, allow, deny, fail_unknown, args.recursive)
        scope = None
        if args.packages:
            scope = ", ".join(args.packages) + (" (including transitive dependencies)" if args.recursive else " (selected packages only)")
        output = render(rows, args.format, policy={"allow": allow, "deny": deny, "fail-unknown": fail_unknown}, scope=scope)
        if args.output:
            args.output.write_text(output, encoding="utf-8")
        else:
            sys.stdout.write(output)
        return 1 if failed else 0
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
