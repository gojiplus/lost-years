"""Lost Years: Expected Number of Years Lost."""

# Get version from package metadata (Python 3.11+ has this built-in)
from importlib.metadata import version

from .hld import lost_years_hld
from .ssa import lost_years_ssa
from .types import ColumnConfig, ColumnMapping, DataSourceConfig, LifeExpectancyResult
from .who import lost_years_who

__version__ = version("lost_years")

__all__ = [
    "lost_years_ssa",
    "lost_years_hld",
    "lost_years_who",
    "ColumnConfig",
    "ColumnMapping",
    "DataSourceConfig",
    "LifeExpectancyResult",
]
