"""TEI source acquisition and source-preserving Text-Fabric conversion."""

from .convert import convert
from .model import ConversionError, Policy

__all__ = ["ConversionError", "Policy", "convert"]
