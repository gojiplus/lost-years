"""Shared helpers for reading input frames and matching to life-table rows."""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd
import requests

if TYPE_CHECKING:
    import numpy as np
    import numpy.typing as npt

# Setup logger
logger = logging.getLogger(__name__)


def isstring(s: Any) -> bool:
    """Report whether ``s`` is a string.

    Args:
        s: Value to test.

    Returns:
        True when ``s`` is a ``str``.
    """
    return isinstance(s, str)


def column_exists(df: pd.DataFrame, col: str | None) -> bool:
    """Check the column name exists in the DataFrame.

    Args:
        df: Pandas DataFrame.
        col: Column name.

    Returns:
        bool: True if exists, False if not exists.

    """
    if col and (col not in df.columns):
        logger.warning("The specified column `%s` was not found in the input file", col)
        return False
    return True


def fixup_columns(cols: list[Any]) -> list[str]:
    """Replace index location column to name with `col` prefix.

    Args:
        cols: List of original columns

    Returns:
        List of column names

    """
    out_cols = []
    for col in cols:
        if isinstance(col, int):
            out_cols.append(f"col{col:d}")
        else:
            out_cols.append(col)
    return out_cols


def closest(lst: "list[float] | npt.NDArray[np.floating[Any]]", c: float) -> float:
    """Find closest value in list or array.

    Args:
        lst: List of floats or numpy array
        c: Target value to find closest match for

    Returns:
        Closest value in the list/array
    """
    working_list: list[float] = lst if isinstance(lst, list) else lst.tolist()
    return working_list[
        min(range(len(working_list)), key=lambda i: abs(working_list[i] - c))
    ]


def download_file(url: str, local_path: str | Path | None = None) -> None:
    """Stream ``url`` to disk.

    Args:
        url: Source URL.
        local_path: Destination path. Defaults to the URL's last path segment.
    """
    match local_path:
        case None:
            local_path = Path(url.split("/")[-1])
        case str():
            local_path = Path(local_path)
        case _:
            pass  # Already a Path object

    # These are multi-megabyte life tables on slow public hosts; the timeout is
    # per-read, not for the whole transfer, so a generous value is safe.
    r = requests.get(url, timeout=60)
    with local_path.open("wb") as f:
        for chunk in r.iter_content(chunk_size=512 * 1024):
            if chunk:  # filter out keep-alive new chunks
                f.write(chunk)
