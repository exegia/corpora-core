"""Validate a version-pinned selection of a caller-authorized archive."""

from __future__ import annotations

import hmac
import io
import tempfile
import zipfile
from pathlib import Path
from typing import cast

import yaml

from .ai_scope import scope_content_hash, scope_nodes
from .ai_types import NodeScope, ScopeLevel, ValidateResponse
from .ai_validation import FeatureType, validate_nodes
from .reader import ArchiveReadNotFound, _load_api
from .validator import MAX_ARCHIVE_BYTES, ArchiveTooLarge, _extract, _members


class StaleScope(ValueError):
    def __init__(self, message: str, current_version: str):
        super().__init__(message)
        self.current_version = current_version


def validate_archive_scope(data: bytes, scope: NodeScope) -> ValidateResponse:
    """Load once and validate only nodes in the requested versioned scope."""
    if len(data) > MAX_ARCHIVE_BYTES:
        raise ArchiveTooLarge(f"Archive exceeds {MAX_ARCHIVE_BYTES} bytes")
    if scope.level != ScopeLevel.corpus and scope.node_id is None:
        raise ValueError("Non-corpus scope requires a node")
    with (
        zipfile.ZipFile(io.BytesIO(data)) as archive,
        tempfile.TemporaryDirectory(prefix="corpus-scope-") as temporary,
    ):
        root = Path(temporary)
        _extract(archive, _members(archive), root)
        manifest_path = root / "manifest.yml"
        manifest = yaml.safe_load(manifest_path.read_text()) if manifest_path.is_file() else None
        if not isinstance(manifest, dict) or not manifest.get("version"):
            raise ValueError("Corpus manifest has no version")
        version = str(manifest["version"])
        if scope.version.removeprefix("v") != version.removeprefix("v"):
            raise StaleScope("Corpus version has changed", version)
        api = _load_api(root)
        if api is None:
            raise ArchiveReadNotFound("Corpus has no Text-Fabric data")
        nodes = scope_nodes(api, scope)
        if scope.content_hash is not None and not hmac.compare_digest(
            scope.content_hash.encode("utf-8"), scope_content_hash(api, nodes).encode("ascii")
        ):
            raise StaleScope("Scoped text has changed", version)
        types, features = api.T.sectionTypes, api.T.sectionFeats
        if len(types) != len(features):
            raise ValueError("Corpus section schema is inconsistent")
        requirements: dict[str, dict[str, FeatureType]] = {}
        for kind, name in zip(types, features, strict=True):
            feature = api.Fs(name)
            metadata = getattr(feature, "meta", {}) or {}
            value_type = getattr(feature, "valueType", None) or metadata.get("value_type")
            if value_type not in ("int", "str"):
                raise ValueError("Corpus section feature has an unsupported value type")
            requirements.setdefault(kind, {})[name] = cast(FeatureType, value_type)
        return validate_nodes(
            api, corpus=scope.corpus, version=version, nodes=nodes, required_features=requirements
        )
