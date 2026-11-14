"""Bounded archive inspection followed by actual TF and CF load cycles."""

from __future__ import annotations

import io
import lzma
import re
import shutil
import stat
import tempfile
import zipfile
import zlib
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

MAX_ARCHIVE_BYTES = 3_000_000
MAX_UNPACKED_BYTES = 64_000_000
MAX_FILES = 3_000
MAX_NODES = 1_000_000
NODE_SPEC = re.compile(r"^[1-9][0-9]*(?:-[1-9][0-9]*)?(?:,[1-9][0-9]*(?:-[1-9][0-9]*)?)*$")
SUPPORTED_SUFFIXES = frozenset({".corpus", ".zip", ".ctei", ".cusx"})


class UnsupportedFormat(ValueError):
    code = "unsupported_format"


class ArchiveTooLarge(ValueError):
    code = "archive_too_large"


def _result(
    name: str,
    *,
    valid: bool,
    reasons: list[str],
    checks: dict[str, bool | None],
    stats: dict[str, int] | None = None,
) -> dict[str, Any]:
    return {
        "corpus": Path(name).stem,
        "path": name,
        "valid": valid,
        "stats": stats,
        "reasons": reasons,
        "checks": checks,
    }


def _members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    infos = archive.infolist()
    if len(infos) > MAX_FILES:
        raise ArchiveTooLarge(f"Archive has more than {MAX_FILES} members")
    if sum(info.file_size for info in infos) > MAX_UNPACKED_BYTES:
        raise ArchiveTooLarge(f"Archive expands past {MAX_UNPACKED_BYTES} bytes")
    names: set[str] = set()
    for info in infos:
        path = PurePosixPath(info.filename)
        if (
            not info.filename
            or path.is_absolute()
            or ".." in path.parts
            or "\\" in info.filename
            or str(path) != info.filename.rstrip("/")
            or str(path) in names
        ):
            raise ValueError("Archive contains an unsafe or duplicate member path")
        names.add(str(path))
        if info.flag_bits & 1 or stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK:
            raise ValueError("Archive contains an encrypted member or symbolic link")
    return infos


def _extract(archive: zipfile.ZipFile, infos: list[zipfile.ZipInfo], root: Path) -> None:
    extracted = 0
    for info in infos:
        target = root.joinpath(*PurePosixPath(info.filename).parts)
        if info.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info) as source, target.open("wb") as output:
            while chunk := source.read(1024 * 1024):
                extracted += len(chunk)
                if extracted > MAX_UNPACKED_BYTES:
                    raise ArchiveTooLarge(f"Archive expands past {MAX_UNPACKED_BYTES} bytes")
                output.write(chunk)


def _stats(api: Any) -> dict[str, int]:
    otype = api.F.otype
    return {
        "max_slot": int(otype.maxSlot),
        "max_node": int(otype.maxNode),
        "node_types": len(otype.all),
        "node_features": len(list(api.Fall())),
        "edge_features": len(list(api.Eall())),
    }


def _plain(value: Any) -> Any:
    """Normalize array and NumPy scalar representations across cache loads."""
    if isinstance(value, Mapping):
        return tuple(sorted(((str(key), _plain(item)) for key, item in value.items())))
    if isinstance(value, (str, bytes, int, float, bool)) or value is None:
        return value
    item = getattr(value, "item", None)
    if callable(item):
        return _plain(item())
    if isinstance(value, (list, tuple, set)) or hasattr(value, "__iter__"):
        items = tuple(_plain(item) for item in value)
        return tuple(sorted(items, key=repr)) if isinstance(value, set) else items
    return repr(value)


def _samples(api: Any) -> tuple[Any, ...]:
    """Compare representative typed values and text across CF load paths."""
    max_node = int(api.F.otype.maxNode)
    nodes = range(1, max_node + 1, max(1, max_node // 12))
    values: list[Any] = []
    for name in sorted(api.Fall()):
        feature = api.Fs(name)
        values.append((name, tuple((node, _plain(feature.v(node))) for node in nodes)))
    for name in sorted(api.Eall()):
        feature = api.Es(name)
        forward = getattr(feature, "f", None) or feature.s
        values.append((name, tuple((node, _plain(forward(node))) for node in nodes)))
    return tuple(values)


def _load_tf(root: Path) -> tuple[dict[str, int], tuple[Any, ...]]:
    from tf.fabric import Fabric

    api = Fabric(locations=str(root), silent="deep").loadAll(silent="deep")
    if not api:
        raise ValueError("Text-Fabric loadAll returned no API")
    return _stats(api), _samples(api)


def _load_cf(root: Path, *, expect_cache: bool) -> tuple[dict[str, int], tuple[Any, ...]]:
    from cfabric.core import Fabric

    fabric = Fabric(locations=str(root), silent="deep")
    api = fabric.loadAll(silent="deep")
    if not api:
        raise ValueError("Context-Fabric loadAll returned no API")
    if expect_cache and not getattr(fabric, "_loaded_from_cfm", False):
        raise ValueError("Context-Fabric recompiled instead of loading the .cfm cache")
    return _stats(api), _samples(api)


def _try_load(loader: Any, *args: Any, **kwargs: Any) -> tuple[Any | None, str | None]:
    try:
        return loader(*args, **kwargs), None
    except Exception as error:
        return None, str(error) or type(error).__name__


def _preflight_node_limit(root: Path) -> None:
    """Reject expansive TF node declarations before any loader allocates arrays."""
    rows = (root / "otype.tf").read_text(encoding="utf-8-sig").splitlines()
    try:
        start = rows.index("") + 1
    except ValueError as error:
        raise ValueError("otype.tf has no metadata separator") from error
    current_node = 0
    for row in rows[start:]:
        if not row:
            continue
        parts = row.split("\t")
        if len(parts) == 1:
            current_node += 1
            if current_node > MAX_NODES:
                raise ValueError(f"otype.tf exceeds {MAX_NODES} nodes")
        elif len(parts) == 2:
            if not NODE_SPEC.fullmatch(parts[0]):
                raise ValueError("otype.tf has an invalid node range")
            for span in parts[0].split(","):
                current_node = max(current_node, *(int(number) for number in span.split("-")))
                if current_node > MAX_NODES:
                    raise ValueError(f"otype.tf exceeds {MAX_NODES} nodes")
        else:
            raise ValueError("otype.tf has an invalid node row")


def _validate_tf(root: Path, name: str, *, shipped_cache: bool) -> dict[str, Any]:
    checks: dict[str, bool | None] = {
        "shipped_cfm_load": None,
        "shipped_cfm_match": None,
    }
    reasons: list[str] = []
    shipped = None
    if shipped_cache:
        shipped, error = _try_load(_load_cf, root, expect_cache=True)
        checks["shipped_cfm_load"] = error is None
        if error:
            reasons.append(f"Shipped .cfm cache failed to load: {error}")

    for cache in (root / ".cfm", root / ".tf"):
        if cache.exists():
            shutil.rmtree(cache)

    tf, tf_error = _try_load(_load_tf, root)
    cf, cf_error = _try_load(_load_cf, root, expect_cache=False)
    warm, warm_error = _try_load(_load_cf, root, expect_cache=True)
    checks.update(
        {
            "text_fabric_load": tf_error is None,
            "context_fabric_load": cf_error is None,
            "cfm_mmap_reload": warm_error is None,
            "stats_match": tf is not None
            and cf is not None
            and tf[0] == cf[0] == (warm[0] if warm else None),
            "samples_match": tf is not None
            and cf is not None
            and warm is not None
            and tf[1] == cf[1] == warm[1],
        }
    )
    for label, error in (
        ("Text-Fabric", tf_error),
        ("Context-Fabric", cf_error),
        ("Context-Fabric mmap reload", warm_error),
    ):
        if error:
            reasons.append(f"{label} failed to load: {error}")
    if not checks["stats_match"] and tf and cf and warm:
        reasons.append("Text-Fabric, Context-Fabric, and mmap statistics differ")
    if not checks["samples_match"] and tf and cf and warm:
        reasons.append("Text-Fabric, Context-Fabric, and mmap feature samples differ")
    if shipped_cache:
        checks["shipped_cfm_match"] = shipped is not None and cf is not None and shipped == cf
        if not checks["shipped_cfm_match"] and shipped and cf:
            reasons.append("Shipped .cfm cache differs from a fresh compilation")
    return _result(
        name,
        valid=all(value is not False for value in checks.values()),
        reasons=reasons,
        checks=checks,
        stats=cf[0] if cf else None,
    )


def validate_archive(data: bytes, name: str) -> dict[str, Any]:
    """Validate a supported archive in a temporary directory; never trust ZIP paths."""
    suffix = Path(name).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise UnsupportedFormat(f"Unsupported corpus archive format: {suffix or '<none>'}")
    if len(data) > MAX_ARCHIVE_BYTES:
        raise ArchiveTooLarge(f"Archive exceeds {MAX_ARCHIVE_BYTES} bytes")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        with archive, tempfile.TemporaryDirectory(prefix="corpora-validate-") as temporary:
            infos = _members(archive)
            if suffix in {".ctei", ".cusx"}:
                from .profiles import validate_ctei, validate_cusx

                validator = validate_ctei if suffix == ".ctei" else validate_cusx
                return validator(archive, infos, name)
            root = Path(temporary)
            _extract(archive, infos, root)
            datasets = list(root.rglob("otype.tf"))
            if len(datasets) != 1:
                return _result(
                    name,
                    valid=False,
                    reasons=["Archive must contain exactly one Text-Fabric otype.tf"],
                    checks={"text_fabric_load": False},
                )
            _preflight_node_limit(datasets[0].parent)
            return _validate_tf(datasets[0].parent, name, shipped_cache=suffix == ".corpus")
    except ArchiveTooLarge:
        raise
    except (
        OSError,
        ValueError,
        RuntimeError,
        zipfile.BadZipFile,
        EOFError,
        zlib.error,
        lzma.LZMAError,
    ) as error:
        return _result(
            name, valid=False, reasons=[f"Unreadable archive: {error}"], checks={"archive": False}
        )
