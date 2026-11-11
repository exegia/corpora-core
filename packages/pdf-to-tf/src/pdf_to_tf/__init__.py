"""Score-gated PDF → TEI → Text-Fabric conversion."""

from .pipeline import ConversionFailed, convert

__all__ = ["ConversionFailed", "convert"]
