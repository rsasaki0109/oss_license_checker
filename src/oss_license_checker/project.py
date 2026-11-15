"""Dependency selection and explicit TOML policy loading."""

import tomllib
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name


def load_policy(path):
    with path.open("rb") as stream:
        document = tomllib.load(stream)
    if path.name == "pyproject.toml":
        tools = document.get("tool", {})
        if not isinstance(tools, dict):
            raise ValueError("Expected [tool.oss-license-checker] table in pyproject.toml")
        policy = tools.get("oss-license-checker")
        if policy is None:
            raise ValueError("Missing [tool.oss-license-checker] in pyproject.toml")
    else:
        policy = document
    if not isinstance(policy, dict):
        raise ValueError("Policy must be a TOML table")
    unknown = policy.keys() - {"allow", "deny", "fail-unknown"}
    if unknown:
        raise ValueError(f"Unknown policy keys: {', '.join(sorted(unknown))}")
    for key in ("allow", "deny"):
        value = policy.get(key, [])
        if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
            raise ValueError(f"Policy '{key}' must be an array of nonempty strings")
    if "fail-unknown" in policy and not isinstance(policy["fail-unknown"], bool):
        raise ValueError("Policy 'fail-unknown' must be a boolean")
    return policy


def dependency_names(installed, roots):
    """Resolve installed Requires-Dist edges, markers and requested extras.

    Inspect this interpreter's environment; never install or resolve from a registry.
    Revisit a distribution when new extras are activated, and stop on cycles.
    """
    if not roots:
        raise ValueError("--recursive requires at least one installed root package")
    pending = [(root, "command line") for root in roots]
    visited = set()
    selected = set()
    while pending:
        text, parent = pending.pop()
        try:
            requirement = Requirement(text)
        except InvalidRequirement as exc:
            raise ValueError(f"Invalid requirement from {parent}: {text}") from exc
        name = canonicalize_name(requirement.name)
        if name not in installed:
            raise ValueError(f"Package is not installed: {name} (required by {parent})")
        dist = installed[name]
        if requirement.specifier and not requirement.specifier.contains(dist.version, prereleases=True):
            raise ValueError(f"Installed {name}=={dist.version} does not satisfy {text} (required by {parent})")
        extras = {canonicalize_name(extra) for extra in requirement.extras}
        provided = {canonicalize_name(extra) for extra in dist.metadata.get_all("Provides-Extra") or []}
        if extras - provided:
            raise ValueError(f"Unknown extras for {name}: {', '.join(sorted(extras - provided))}")
        selected.add(name)
        for extra in {""} | extras:
            if (name, extra) in visited:
                continue
            visited.add((name, extra))
            for raw in dist.metadata.get_all("Requires-Dist") or []:
                try:
                    child = Requirement(raw)
                except InvalidRequirement as exc:
                    raise ValueError(f"Invalid requirement from {name}: {raw}") from exc
                if child.marker is None or child.marker.evaluate({"extra": extra}):
                    pending.append((str(child), name))
    return sorted(selected)
