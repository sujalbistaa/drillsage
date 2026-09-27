"""DrillSage: offset-well drilling intelligence (SIH26121, Oil India Limited)."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("drillsage")
except PackageNotFoundError:  # pragma: no cover - only when running from an uninstalled tree
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
