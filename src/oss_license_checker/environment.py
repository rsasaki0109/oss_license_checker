"""Index distributions in metadata discovery order (first match wins)."""

from packaging.utils import canonicalize_name


def installed_distributions(distributions):
    installed = {}
    for distribution in distributions:
        name = distribution.metadata.get('Name')
        if name:
            installed.setdefault(canonicalize_name(name), distribution)
    return installed
