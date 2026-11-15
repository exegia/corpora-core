"""Pure, bounded preparation of stored-corpus edits; no storage or authorization.

The caller must authorize the owner, resolve the immutable input and snapshot
revisions, and atomically compare-and-swap the returned archive and history.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

import yaml

from .reader import _load_api
from .validator import MAX_ARCHIVE_BYTES, ArchiveTooLarge, _extract, _members, validate_archive

MANIFEST_FIELDS = frozenset(
    {
        "name",
        "description",
        "version",
        "language",
        "languageCode",
        "type",
        "category",
        "written_date",
    }
)
_VERSION = re.compile(r"^v?1\.(\d+)$")


@dataclass(frozen=True)
class PreparedEdit:
    archive: bytes
    version: str
    digest: str
    result: dict[str, Any]


def _digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _uuid(value: str) -> str:
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError) as error:
        raise ValueError("trusted owner and revision IDs must be UUIDs") from error


def _validated_zip(data: bytes) -> tuple[zipfile.ZipFile, list[zipfile.ZipInfo]]:
    if len(data) > MAX_ARCHIVE_BYTES:
        raise ArchiveTooLarge("Archive exceeds size limit")
    archive = zipfile.ZipFile(io.BytesIO(data))
    try:
        return archive, _members(archive)
    except Exception:
        archive.close()
        raise


def _mapping(data: bytes, label: str) -> dict[str, Any]:
    try:
        value = yaml.safe_load(data)
    except yaml.YAMLError as error:
        raise ValueError(f"{label} is missing or invalid") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} is missing or invalid")
    return value


def _require_corpus_name(name: str) -> None:
    if (
        not name
        or name in (".", "..")
        or "/" in name
        or "\\" in name
        or len(name.encode("utf-8")) > 255
        or any(ord(character) < 32 for character in name)
        or not name.endswith(".corpus")
    ):
        raise ValueError("Only a plain .corpus archive name is editable")


def _update_toc(data: bytes, old_version: str, new_version: str) -> bytes | None:
    toc = _mapping(data, "Table of contents")
    if "version" not in toc:
        return None
    old = str(toc["version"])
    if old.removeprefix("v") != old_version.removeprefix("v"):
        raise ValueError("Table of contents version does not match manifest")
    toc["version"] = new_version if old.startswith("v") else new_version.removeprefix("v")
    return yaml.safe_dump(toc, allow_unicode=True, sort_keys=False).encode()


def _baseline_history(expected_version: str, current_revision: str) -> bytes:
    # Missing history is not evidence of a conversion author or timestamp.
    return yaml.safe_dump(
        {
            "versions": [
                {
                    "id": expected_version,
                    "label": expected_version,
                    "title": "Packaged snapshot",
                    "at": "",
                    "current": True,
                    "snapshot_revision": current_revision,
                    "snapshot_key": None,
                    "author": None,
                    "approved_by": None,
                    "notes": [],
                    "files": [],
                }
            ]
        },
        sort_keys=False,
    ).encode()


def _history(data: bytes, expected_version: str, current_revision: str) -> tuple[dict, str]:
    history = _mapping(data, "Version history")
    versions = history.get("versions")
    if not isinstance(versions, list) or any(not isinstance(row, dict) for row in versions):
        raise ValueError("Version history is missing or invalid")
    if any("current" in row and not isinstance(row["current"], bool) for row in versions):
        raise ValueError("Version history has an invalid current flag")
    current = [row for row in versions if row.get("current") is True]
    if len(current) != 1 or str(current[0].get("label") or current[0].get("id") or "").removeprefix(
        "v"
    ) != expected_version.removeprefix("v"):
        raise ValueError("Version history does not match current HEAD")
    existing_revision = current[0].get("snapshot_revision")
    if existing_revision is not None and existing_revision != current_revision:
        raise ValueError("Version history revision does not match current HEAD")
    parsed = [
        int(match.group(1))
        for row in versions
        for key in ("id", "label")
        if (match := _VERSION.fullmatch(str(row.get(key, ""))))
    ]
    head = _VERSION.fullmatch(expected_version)
    if head is None:
        raise ValueError("Corpus version must use 1.minor notation")
    next_version = f"v1.{max([int(head.group(1)), *parsed]) + 1}"
    current[0]["current"] = False
    current[0]["snapshot_revision"] = current_revision
    return history, next_version


def _require_new_revision(history: dict, new_revision: str) -> None:
    revisions = [
        _uuid(value)
        for row in history["versions"]
        if (value := row.get("snapshot_revision")) is not None
    ]
    if len(revisions) != len(set(revisions)) or new_revision in revisions:
        raise ValueError("Version history contains a reused snapshot revision")


def prepare_edit(
    data: bytes,
    *,
    name: str,
    expected_digest: str,
    expected_version: str,
    owner: str,
    current_revision: str,
    new_revision: str,
    operation: Literal["manifest", "node"],
    updates: dict[str, Any],
    node: int | None = None,
) -> PreparedEdit:
    """Prepare one edit from a verified, owner-selected corpus snapshot.

    Revision IDs are server-owned opaque identifiers, not storage paths. A
    successful result is not published until the caller atomically advances
    its head and records this exact digest and version.
    """
    _require_corpus_name(name)
    owner, current_revision, new_revision = map(_uuid, (owner, current_revision, new_revision))
    if current_revision == new_revision:
        raise ValueError("New revision must differ from current HEAD")
    if _digest(data) != expected_digest:
        raise ValueError("Corpus digest is stale")
    if not isinstance(updates, dict):
        raise ValueError("Updates must be an object")
    try:
        update_size = len(json.dumps(updates, ensure_ascii=False).encode())
    except (TypeError, ValueError) as error:
        raise ValueError("Updates must be JSON values") from error
    if update_size > MAX_ARCHIVE_BYTES:
        raise ArchiveTooLarge("Edit request exceeds size limit")
    verdict = validate_archive(data, "input.corpus")
    if not verdict.get("valid"):
        raise ValueError("Corpus archive is invalid")
    source, infos = _validated_zip(data)
    with source, tempfile.TemporaryDirectory(prefix="corpus-edit-") as temporary:
        root = Path(temporary)
        _extract(source, infos, root)
        manifest_path, history_path = root / "manifest.yml", root / "history.yml"
        if not manifest_path.is_file():
            raise ValueError("Corpus manifest is required")
        manifest = _mapping(manifest_path.read_bytes(), "Manifest")
        if str(manifest.get("version", "")).removeprefix("v") != expected_version.removeprefix("v"):
            raise ValueError("Corpus version is stale")
        history_data = (
            history_path.read_bytes()
            if history_path.is_file()
            else _baseline_history(expected_version, current_revision)
        )
        history, next_version = _history(history_data, expected_version, current_revision)
        _require_new_revision(history, new_revision)
        result: dict[str, Any]
        changes = ["manifest.yml"]
        if operation == "manifest":
            patch = {key: value for key, value in updates.items() if key in MANIFEST_FIELDS}
            if not patch or any(
                value is not None and not isinstance(value, str) for value in patch.values()
            ):
                raise ValueError("Manifest update requires string or null fields")
            manifest.update(patch)
            title = "Updated metadata"
            result = manifest
        elif operation == "node":
            if type(node) is not int or node < 1:
                raise ValueError("A positive node ID is required")
            patch = {
                key: updates[key]
                for key in ("otype", "note")
                if key in updates and updates[key] is not None
            }
            if not patch or any(not isinstance(value, str) for value in patch.values()):
                raise ValueError("Node annotation requires an otype or note")
            if "otype" in patch:
                patch["otype"] = patch["otype"].strip()
                if not patch["otype"]:
                    raise ValueError("Node type cannot be blank")
            api = _load_api(root)
            actual = api.F.otype.v(node) if api else None
            if actual is None:
                raise ValueError("Node is not present in the corpus")
            sidecar = root / "annotations.json"
            try:
                annotations = (
                    json.loads(sidecar.read_bytes()) if sidecar.exists() else {"nodes": {}}
                )
            except (OSError, ValueError) as error:
                raise ValueError("Node annotations are invalid") from error
            if not isinstance(annotations, dict) or not isinstance(annotations.get("nodes"), dict):
                raise ValueError("Node annotations are invalid")
            existing = annotations["nodes"].get(str(node), {})
            if not isinstance(existing, dict) or existing.get(
                "converted_otype", str(actual)
            ) != str(actual):
                raise ValueError("Node annotation conflicts with source type")
            entry = {
                **existing,
                **patch,
                "converted_otype": str(actual),
                "updated_at": datetime.now(UTC).isoformat(),
            }
            annotations["nodes"][str(node)] = entry
            sidecar.write_text(json.dumps(annotations, ensure_ascii=False, indent=2) + "\n")
            changes.append("annotations.json")
            result = {"node": node, **entry}
            title = "Annotated node"
        else:
            raise ValueError("Unsupported edit operation")
        toc_path = root / "toc.yml"
        if toc_path.is_file():
            toc_bytes = _update_toc(toc_path.read_bytes(), expected_version, next_version)
            if toc_bytes is not None:
                toc_path.write_bytes(toc_bytes)
                changes.append("toc.yml")
        manifest["version"] = next_version.removeprefix("v")
        manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False))
        history["versions"].append(
            {
                "id": next_version,
                "label": next_version,
                "title": title,
                "at": datetime.now(UTC).isoformat(),
                "current": True,
                "snapshot_revision": new_revision,
                "snapshot_key": None,
                "author": {"sub": owner},
                "approved_by": None,
                "notes": [],
                "files": [
                    {
                        "path": name,
                        "kind": "modified"
                        if name in {item.filename for item in infos}
                        else "added",
                    }
                    for name in changes
                ],
            }
        )
        history_path.write_text(yaml.safe_dump(history, allow_unicode=True, sort_keys=False))
        output = io.BytesIO()
        changed = {"manifest.yml", "history.yml", *changes}
        with zipfile.ZipFile(output, "w") as target:
            for info in infos:
                path = root / info.filename
                if info.filename in changed:
                    target.writestr(info, path.read_bytes())
                else:
                    target.writestr(info, source.read(info))
            if "history.yml" not in {info.filename for info in infos}:
                target.writestr(
                    "history.yml", history_path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED
                )
            if operation == "node" and "annotations.json" not in {info.filename for info in infos}:
                target.writestr(
                    "annotations.json",
                    (root / "annotations.json").read_bytes(),
                    compress_type=zipfile.ZIP_DEFLATED,
                )
        result_data = output.getvalue()
        if len(result_data) > MAX_ARCHIVE_BYTES:
            raise ArchiveTooLarge("Edited archive exceeds size limit")
        if not validate_archive(result_data, "edited.corpus").get("valid"):
            raise ValueError("Edited corpus archive is invalid")
        return PreparedEdit(
            archive=result_data, version=next_version, digest=_digest(result_data), result=result
        )


def prepare_restore(
    current_data: bytes,
    selected_data: bytes,
    *,
    name: str,
    expected_digest: str,
    selected_digest: str,
    expected_version: str,
    selected_version: str,
    owner: str,
    current_revision: str,
    selected_revision: str,
    new_revision: str,
) -> PreparedEdit:
    """Prepare a new revision from an authorized historical snapshot.

    The caller supplies owner-resolved bytes and registry revision IDs. This
    operation preserves the current timeline and never rewinds its head. It
    does not authenticate the caller or publish a storage object.
    """
    _require_corpus_name(name)
    owner, current_revision, selected_revision, new_revision = map(
        _uuid, (owner, current_revision, selected_revision, new_revision)
    )
    if len({current_revision, selected_revision, new_revision}) != 3:
        raise ValueError("Restore requires distinct current, selected and new revisions")
    if _digest(current_data) != expected_digest or _digest(selected_data) != selected_digest:
        raise ValueError("Corpus or selected snapshot digest is stale")
    if not validate_archive(current_data, "current.corpus").get("valid"):
        raise ValueError("Current corpus archive is invalid")
    if not validate_archive(selected_data, "selected.corpus").get("valid"):
        raise ValueError("Selected corpus archive is invalid")
    current, current_infos = _validated_zip(current_data)
    try:
        selected, selected_infos = _validated_zip(selected_data)
    except Exception:
        current.close()
        raise
    with current, selected:
        current_names = {entry.filename for entry in current_infos}
        selected_names = {entry.filename for entry in selected_infos}
        if (
            not {"manifest.yml", "history.yml"} <= current_names
            or "manifest.yml" not in selected_names
        ):
            raise ValueError("Corpus manifest and current version history are required")
        current_manifest = _mapping(current.read("manifest.yml"), "Current manifest")
        selected_manifest = _mapping(selected.read("manifest.yml"), "Selected manifest")
        if str(current_manifest.get("version", "")).removeprefix(
            "v"
        ) != expected_version.removeprefix("v"):
            raise ValueError("Corpus version is stale")
        if str(selected_manifest.get("version", "")).removeprefix(
            "v"
        ) != selected_version.removeprefix("v"):
            raise ValueError("Selected snapshot version does not match")
        if "toc.yml" in current_names:
            _update_toc(current.read("toc.yml"), expected_version, expected_version)
        current_uid = current_manifest.get("uid")
        selected_uid = selected_manifest.get("uid")
        if current_uid != selected_uid and (current_uid is not None or selected_uid is not None):
            raise ValueError("Selected snapshot belongs to another corpus")
        history, next_version = _history(
            current.read("history.yml"), expected_version, current_revision
        )
        _require_new_revision(history, new_revision)
        candidates = [
            row
            for row in history["versions"]
            if row.get("snapshot_revision") == selected_revision
            and selected_version.removeprefix("v")
            in {
                str(row.get("id", "")).removeprefix("v"),
                str(row.get("label", "")).removeprefix("v"),
            }
        ]
        if len(candidates) != 1:
            raise ValueError("Selected revision is absent or ambiguous in current history")
        selected_manifest["version"] = next_version.removeprefix("v")
        manifest_bytes = yaml.safe_dump(
            selected_manifest, allow_unicode=True, sort_keys=False
        ).encode()
        toc_bytes = (
            _update_toc(selected.read("toc.yml"), selected_version, next_version)
            if "toc.yml" in selected_names
            else None
        )
        changed = []
        names = (current_names | selected_names) - {"history.yml", "manifest.yml"}
        for name in sorted(names):
            if name.endswith("/"):
                continue
            if name not in current_names:
                kind = "added"
            elif name not in selected_names:
                kind = "removed"
            elif current.read(name) != (
                toc_bytes if name == "toc.yml" and toc_bytes is not None else selected.read(name)
            ):
                kind = "modified"
            else:
                continue
            changed.append({"path": name, "kind": kind})
        changed.extend(
            [
                {"path": "manifest.yml", "kind": "modified"},
                {"path": "history.yml", "kind": "modified"},
            ]
        )
        history["versions"].append(
            {
                "id": next_version,
                "label": next_version,
                "title": "Restored version",
                "at": datetime.now(UTC).isoformat(),
                "current": True,
                "snapshot_revision": new_revision,
                "snapshot_key": None,
                "author": {"sub": owner},
                "approved_by": None,
                "notes": [],
                "files": changed,
                "restored_from": {
                    "version": selected_version,
                    "snapshot_revision": selected_revision,
                },
            }
        )
        history_bytes = yaml.safe_dump(history, allow_unicode=True, sort_keys=False).encode()
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as target:
            for info in selected_infos:
                if info.filename == "manifest.yml":
                    target.writestr(info, manifest_bytes)
                elif info.filename == "history.yml":
                    target.writestr(info, history_bytes)
                elif info.filename == "toc.yml" and toc_bytes is not None:
                    target.writestr(info, toc_bytes)
                else:
                    target.writestr(info, selected.read(info))
            if "history.yml" not in selected_names:
                target.writestr("history.yml", history_bytes, compress_type=zipfile.ZIP_DEFLATED)
        result_data = output.getvalue()
        if len(result_data) > MAX_ARCHIVE_BYTES:
            raise ArchiveTooLarge("Restored archive exceeds size limit")
        if not validate_archive(result_data, "restored.corpus").get("valid"):
            raise ValueError("Restored corpus archive is invalid")
        return PreparedEdit(
            archive=result_data,
            version=next_version,
            digest=_digest(result_data),
            result=selected_manifest,
        )
