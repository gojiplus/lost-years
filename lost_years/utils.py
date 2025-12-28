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
        logger.warning(f"The specify column `{col!s}` not found in the input file")
        return False
    else:
        return True


def fixup_columns(cols: list[Any]) -> list[str]:
    """Replace index location column to name with `col` prefix

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
    # Convert numpy array to list if needed
    working_list: list[float]
    if hasattr(lst, "tolist"):  # numpy array
        working_list = lst.tolist()  # type: ignore[attr-defined]
    else:
        working_list = lst  # type: ignore[assignment]
    return working_list[min(range(len(working_list)), key=lambda i: abs(working_list[i] - c))]


def download_file(url: str, local_path: str | Path | None = None) -> None:
    match local_path:
        case None:
            local_path = Path(url.split("/")[-1])
        case str():
            local_path = Path(local_path)
        case _:
            pass  # Already a Path object

    r = requests.get(url)
    with local_path.open("wb") as f:
        for chunk in r.iter_content(chunk_size=512 * 1024):
            if chunk:  # filter out keep-alive new chunks
                f.write(chunk)
