"""Lost Years: Expected Number of Years Lost."""

from .hld import lost_years_hld
from .ssa import lost_years_ssa
from .who import lost_years_who

# Get version from package metadata
try:
    from importlib.metadata import version as get_version
except ImportError:
    from importlib_metadata import version as get_version

__version__ = get_version("lost_years")

__all__ = ["lost_years_ssa", "lost_years_hld", "lost_years_who"]
