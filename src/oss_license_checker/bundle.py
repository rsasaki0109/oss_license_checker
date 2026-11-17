"""Collect installed license evidence into a ZIP with a SHA-256 manifest."""

import hashlib
from importlib import metadata
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import zipfile

from packaging.utils import canonicalize_name
from packaging.version import Version
from .environment import installed_distributions


EVIDENCE_NAME = re.compile(r"^(?:licen[cs]e|copying|notice|copyright)(?:[._-].*)?$", re.I)


def relative_path(value):
    text = str(value)
    path = PurePosixPath(text)
    if not text or path.is_absolute() or ".." in path.parts or "\\" in text or ":" in text:
        raise ValueError(f"Unsafe license evidence path: {text!r}")
    return path


def create_bundle(rows, target):
    installed = installed_distributions(metadata.distributions())
    packages, contents = [], {}
    target = target.resolve()
    for row in rows:
        name = canonicalize_name(row["name"], validate=True)
        version = str(Version(row["version"]))
        dist = installed.get(name)
        if dist is None or dist.version != row["version"]:
            raise ValueError(f"Installed package changed while collecting evidence: {name}")
        declared = [relative_path(value) for value in dist.metadata.get_all("License-File") or []]
        candidates = {}
        matched = set()
        for entry in dist.files or []:
            raw = PurePosixPath(str(entry))
            # Ignore normal wheel entries outside site-packages (e.g. scripts).
            legal_directory = any(part.endswith('.dist-info') and index + 1 < len(raw.parts)
                                  and raw.parts[index + 1] == 'licenses' for index, part in enumerate(raw.parts))
            declarations = {str(item) for item in declared if str(raw) == str(item)
                            or str(raw).endswith('.dist-info/licenses/' + str(item))
                            or str(raw).endswith('.dist-info/' + str(item))}
            if not (EVIDENCE_NAME.fullmatch(raw.name) or legal_directory or declarations):
                continue
            safe = relative_path(entry)
            candidates[str(safe)] = entry
            matched.update(declarations)
        record = {**row, "files": [], "missing_declared_files": sorted(set(map(str, declared)) - matched)}
        if candidates:
            root = Path(dist.locate_file("")).resolve()
            for source, entry in sorted(candidates.items()):
                location = Path(dist.locate_file(entry)).resolve()
                if not location.is_relative_to(root):
                    raise ValueError(f"License evidence escapes installation directory: {source}")
                if location == target:
                    raise ValueError("Bundle output must not overwrite a source license file")
                data = location.read_bytes()
                archive_path = f"{name}-{version}/files/{source}"
                contents[archive_path] = data
                record["files"].append({"source": source, "path": archive_path,
                                        "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)})
        record["evidence_status"] = "collected" if record["files"] and not record["missing_declared_files"] else "missing"
        packages.append(record)
    manifest = {"schema_version": 1, "packages": packages}
    # Publish only a completed bundle; an error leaves any existing file intact.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, suffix='.zip', delete=False) as stream:
            temporary = Path(stream.name)
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
            for path, data in sorted(contents.items()):
                archive.writestr(path, data)
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return any(package["evidence_status"] == "missing" for package in packages)
