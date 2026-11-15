"""Reviewed license corrections limited to an exact installed version."""

from packaging.licenses import canonicalize_license_expression
from packaging.utils import canonicalize_name
from packaging.version import Version


def validate_overrides(overrides):
    if not isinstance(overrides, dict):
        raise ValueError("Policy 'overrides' must be a table of package names")
    result = {}
    for package, entry in overrides.items():
        name = canonicalize_name(package, validate=True)
        if name in result:
            raise ValueError(f"Duplicate normalized override package: {name}")
        if not isinstance(entry, dict) or set(entry) != {"license", "version", "reason"}:
            raise ValueError(f"Override for {name} requires exactly license, version and reason")
        if any(not isinstance(value, str) or not value.strip() for value in entry.values()):
            raise ValueError(f"Override for {name} requires nonempty string values")
        Version(entry["version"])
        result[name] = {**entry, "license": canonicalize_license_expression(entry["license"])}
    return result
