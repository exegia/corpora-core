"""Run a bounded Text-Fabric expert over a verified text selection."""

from .api import CodexExpert, ResolveError, Selection, apply_resolution, inspect_selection, resolve

__all__ = [
    "CodexExpert",
    "ResolveError",
    "Selection",
    "apply_resolution",
    "inspect_selection",
    "resolve",
]
