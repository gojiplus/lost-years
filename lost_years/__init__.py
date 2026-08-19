"""Lost Years: Expected Number of Years Lost."""

from importlib.metadata import version

from .datasets import TableUnavailableError, ValidationError, data_dir
from .hld import lost_years_hld
from .ssa import lost_years_ssa
from .who import lost_years_who

__version__ = version("lost_years")

__all__ = [
    "TableUnavailableError",
    "ValidationError",
    "data_dir",
    "lost_years_hld",
    "lost_years_ssa",
    "lost_years_who",
]
