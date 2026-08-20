"""The life-table sources ``lost_years update`` knows how to install."""

from .base import Source, SourceUnavailableError
from .hld import HLD
from .ssa import SSA
from .who import WHO

REGISTRY: dict[str, Source] = {source.name: source for source in (HLD(), SSA(), WHO())}

__all__ = ["HLD", "REGISTRY", "SSA", "WHO", "Source", "SourceUnavailableError"]


def get_source(name: str) -> Source:
    """Look up one source by name.

    Args:
        name: Source name, e.g. ``"hld"``.

    Returns:
        The source.

    Raises:
        KeyError: When no source has that name.
    """
    try:
        return REGISTRY[name]
    except KeyError:
        known = ", ".join(sorted(REGISTRY))
        raise KeyError(f"unknown source {name!r}; known sources are {known}") from None
