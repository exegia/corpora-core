"""Run a bounded Text-Fabric expert over a verified text selection."""

from .api import CodexExpert, ResolveError, Selection, inspect_selection, resolve

__all__ = ["CodexExpert", "ResolveError", "Selection", "inspect_selection", "resolve"]
