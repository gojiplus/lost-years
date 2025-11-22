"""Lost Years: Expected Number of Years Lost."""

from .hld import lost_years_hld
from .ssa import lost_years_ssa
from .who import lost_years_who

__version__ = "0.4.0"
__all__ = ["lost_years_ssa", "lost_years_hld", "lost_years_who"]
