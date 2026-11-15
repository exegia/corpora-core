"""Transport-neutral values for scoped corpus validation."""

from dataclasses import dataclass
from enum import StrEnum


class ScopeLevel(StrEnum):
    word = "word"
    passage = "passage"
    section = "section"
    document = "document"
    corpus = "corpus"


@dataclass(frozen=True)
class UnitRange:
    start: int
    end: int


@dataclass(frozen=True)
class NodeScope:
    corpus: str
    level: ScopeLevel
    label: str
    version: str
    node_id: int | None = None
    node_type: str | None = None
    unit_range: UnitRange | None = None
    content_hash: str | None = None


class Severity(StrEnum):
    error = "error"
    warn = "warn"
    info = "info"


@dataclass(frozen=True)
class Finding:
    node_id: int
    node_type: str
    rule: str
    severity: Severity
    message: str
    consequence: str
    fixable: bool
    unfixable_reason: str | None = None
    suggestion_id: str | None = None


@dataclass(frozen=True)
class ValidateResponse:
    corpus: str
    version: str
    checked_nodes: int
    findings: list[Finding]
