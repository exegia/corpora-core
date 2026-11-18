"""Bounded edits of corpus archives; persistence and authorization belong to the caller."""

from __future__ import annotations

import io
import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import yaml
from cfabric import Fabric as ContextFabric
from tf.fabric import Fabric

from .reader import _load_api, _tf_root
from .validator import (
    MAX_ARCHIVE_BYTES,
    ArchiveTooLarge,
    _extract,
    _members,
    _plain,
    validate_archive,
)


def _same_source_and_cache(source: Any, mapped: Any) -> bool:
    """Check every typed node and edge value before rebuilding an old cache."""
    for attribute in ("formats", "defaultFormat", "sectionTypes", "sectionFeats"):
        if _plain(getattr(source.T, attribute)) != _plain(getattr(mapped.T, attribute)):
            return False
    for listing, accessor in (("Fall", "Fs"), ("Eall", "Es")):
        names = set(getattr(source, listing)())
        if names != set(getattr(mapped, listing)()):
            return False
        for name in names:
            left = getattr(source, accessor)(name).items()
            right = getattr(mapped, accessor)(name).items()
            if {int(k): _plain(v) for k, v in left} != {int(k): _plain(v) for k, v in right}:
                return False
    return True


def edit_archive(
    data: bytes,
    *,
    manifest: dict[str, Any] | None = None,
    node: int | None = None,
    features: dict[str, str | int | None] | None = None,
) -> bytes:
    """Return a validated archive with manifest or node features changed.

    Node text is represented by its Text-Fabric features, whose names differ by
    corpus (for example ``word`` or ``text``). Structural features are immutable.
    A caller must publish the returned bytes as a new version after authorization.
    """
    if (manifest is None) == (features is None):
        raise ValueError("Specify exactly one manifest or node edit")
    try:
        request_size = len(
            json.dumps(manifest if manifest is not None else features, allow_nan=False).encode()
        )
    except (TypeError, ValueError) as error:
        raise ValueError("Edit must contain JSON values") from error
    if request_size > MAX_ARCHIVE_BYTES:
        raise ArchiveTooLarge("Edit exceeds size limit")
    if not validate_archive(data, "input.corpus")["valid"]:
        raise ValueError("Input corpus is invalid")
    with (
        zipfile.ZipFile(io.BytesIO(data)) as source,
        tempfile.TemporaryDirectory(prefix="corpus-edit-") as temporary,
    ):
        infos = _members(source)
        root = Path(temporary)
        _extract(source, infos, root)
        changed: dict[str, bytes] = {}
        omitted_prefix = None
        if manifest is not None:
            path = root / "manifest.yml"
            if not path.is_file() or not isinstance(manifest, dict) or not manifest:
                raise ValueError("Manifest edit requires an existing manifest and fields")
            original = yaml.safe_load(path.read_bytes())
            if not isinstance(original, dict) or any(
                not isinstance(k, str) or not k for k in manifest
            ):
                raise ValueError("Manifest must be an object with string keys")
            original.update(manifest)
            changed["manifest.yml"] = yaml.safe_dump(
                original, allow_unicode=True, sort_keys=False
            ).encode()
        else:
            tf_root = _tf_root(root)
            if (
                tf_root is None
                or type(node) is not int
                or node < 1
                or not isinstance(features, dict)
                or not features
            ):
                raise ValueError("Node edit requires an existing node and feature changes")
            mapped_before = _load_api(root)
            # Never trust compiled TF artifacts included by the archive.
            omitted_prefix = (tf_root / ".tf").relative_to(root).as_posix() + "/"
            shutil.rmtree(tf_root / ".tf", ignore_errors=True)
            api = Fabric(locations=str(tf_root), silent="deep").loadAll(silent="deep")
            if not api or api.F.otype.v(node) is None:
                raise ValueError("Node is not present")
            if mapped_before is None or not _same_source_and_cache(api, mapped_before):
                raise ValueError("Source and Context-Fabric cache do not match")
            names = set(api.Fall()) - {"otype"}
            reserved = set(api.Eall()) | {"otype", "otext"}
            if any(
                not isinstance(name, str)
                or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,127}", name)
                or name in reserved
                for name in features
            ):
                raise ValueError("Node feature is invalid or structural")
            existing_files = {path.name.casefold(): path.name for path in tf_root.iterdir()}
            if any(
                (existing := existing_files.get((name + ".tf").casefold())) is not None
                and existing != name + ".tf"
                for name in features
            ):
                raise ValueError("Node feature collides with an existing file")
            replacements: dict[str, dict[int, Any]] = {}
            metadata = {}
            for name, value in features.items():
                feature = api.Fs(name) if name in names else None
                if feature is None and value is None:
                    raise ValueError("Cannot remove an unknown node feature")
                kind = (
                    feature.meta.get("valueType")
                    if feature
                    else ("int" if type(value) is int else "str")
                )
                if value is not None and type(value) is not (int if kind == "int" else str):
                    raise ValueError("Node feature value has the wrong type")
                values = dict(feature.items()) if feature else {}
                if value is None:
                    values.pop(node, None)
                else:
                    values[node] = value
                replacements[name] = values
                metadata[name] = dict(feature.meta) if feature else {"valueType": kind}
            if not Fabric(locations=str(tf_root), silent="deep").save(
                nodeFeatures=replacements, metaData=metadata, silent="deep"
            ):
                raise ValueError("Could not save Text-Fabric features")
            cache_paths = list((tf_root / ".cfr").rglob("*.cfr"))
            if len(cache_paths) != 1:
                raise ValueError("Exactly one Context-Fabric cache is required")
            cache = cache_paths[0]
            cache.unlink()
            fabric = ContextFabric(locations=str(tf_root), silent="deep")
            if not fabric.loadAll(silent="deep"):
                raise ValueError("Edited Text-Fabric cannot load")
            for generated in (tf_root / ".cfr").rglob("*.cfr"):
                generated.unlink()
            fabric.compile(str(cache), silent="deep")
            if not cache.is_file():
                raise ValueError("Edited Context-Fabric cache was not created")
            for name in features:
                path = tf_root / (name + ".tf")
                changed[path.relative_to(root).as_posix()] = path.read_bytes()
            changed[cache.relative_to(root).as_posix()] = cache.read_bytes()
            mapped = _load_api(root)
            if mapped is None or any(
                mapped.Fs(name).v(node) != value for name, value in features.items()
            ):
                raise ValueError("Edited Context-Fabric cache does not match the changes")
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as target:
            for info in infos:
                if omitted_prefix and info.filename.startswith(omitted_prefix):
                    continue
                target.writestr(info, changed.get(info.filename, source.read(info)))
            original_names = {info.filename for info in infos}
            for name in sorted(changed.keys() - original_names):
                target.writestr(name, changed[name])
        result = output.getvalue()
    if len(result) > MAX_ARCHIVE_BYTES:
        raise ArchiveTooLarge("Edited archive exceeds size limit")
    if not validate_archive(result, "edited.corpus")["valid"]:
        raise ValueError("Edited corpus failed validation")
    return result
