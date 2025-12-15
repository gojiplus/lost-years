from pathlib import Path
from typing import Any

import pandas as pd
import requests


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
        print(f"The specify column `{col!s}` not found in the input file")
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


def closest(lst: list[float] | Any, c: float) -> float:
    """Find closest value in list or array.

    Args:
        lst: List of floats or numpy array
        c: Target value to find closest match for

    Returns:
        Closest value in the list/array
    """
    if hasattr(lst, "tolist"):  # numpy array
        lst = lst.tolist()
    return lst[min(range(len(lst)), key=lambda i: abs(lst[i] - c))]


def download_file(url: str, local_path: str | Path | None = None) -> None:
    if local_path is None:
        local_path = Path(url.split("/")[-1])
    elif isinstance(local_path, str):
        local_path = Path(local_path)

    r = requests.get(url)
    with open(local_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=512 * 1024):
            if chunk:  # filter out keep-alive new chunks
                f.write(chunk)
