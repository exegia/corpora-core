"""Explicit conversion policy and source/projection records."""

from dataclasses import dataclass, field
from typing import Any


class ConversionError(ValueError):
    """Input cannot be converted without an unresolved ambiguity or data loss."""


@dataclass(frozen=True)
class Policy:
    choice: str = "reject"
    apparatus: str = "reject"
    witness: str | None = None
    notes: str = "separate"
    allow_no_namespace: bool = False
    max_slots: int = 1_000_000
    max_memberships: int = 10_000_000
    milestones: str = "offsets"
    facsimile: str = "ignore"

    def __post_init__(self) -> None:
        if self.milestones not in {"offsets", "pages"}:
            raise ConversionError("milestones must be offsets or pages")
        if self.facsimile not in {"ignore", "zones"}:
            raise ConversionError("facsimile must be ignore or zones")
        if self.max_slots < 1 or self.max_memberships < 1:
            raise ConversionError("Graph limits must be positive")
        if self.choice not in {"reject", "original", "edited"}:
            raise ConversionError("choice must be reject, original or edited")
        if self.apparatus not in {"reject", "lemma", "witness"}:
            raise ConversionError("apparatus must be reject, lemma or witness")
        if self.notes not in {"separate", "include"}:
            raise ConversionError("notes must be separate or include")
        if (self.apparatus == "witness") != bool(self.witness):
            raise ConversionError("witness is required only for apparatus=witness")


@dataclass(frozen=True)
class Source:
    name: str
    origin: str
    data: bytes
    revision: str | None = None


@dataclass
class Element:
    key: str
    tag: str
    namespace: str
    attributes: dict[str, str]
    parent: str | None
    start: int
    end: int = 0
    line: int | None = None


@dataclass
class Region:
    kind: str
    start: int
    end: int
    blocks: list[tuple[int, int, str]] = field(default_factory=list)


@dataclass
class Document:
    id: str
    source: str
    locator: str
    metadata: dict[str, Any]
    text: str = ""
    elements: list[Element] = field(default_factory=list)
    regions: list[Region] = field(default_factory=list)
    excluded: list[dict[str, Any]] = field(default_factory=list)
    outline: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
