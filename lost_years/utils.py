import requests


def isstring(s):
    return isinstance(s, str)


def column_exists(df, col):
    """Check the column name exists in the DataFrame.

    Args:
        df (:obj:`DataFrame`): Pandas DataFrame.
        col (str): Column name.

    Returns:
        bool: True if exists, False if not exists.

    """
    if col and (col not in df.columns):
        print(f"The specify column `{col!s}` not found in the input file")
        return False
    else:
        return True


def fixup_columns(cols):
    """Replace index location column to name with `col` prefix

    Args:
        cols (list): List of original columns

    Returns:
        list: List of column names

    """
    out_cols = []
    for col in cols:
        if isinstance(col, int):
            out_cols.append(f"col{col:d}")
        else:
            out_cols.append(col)
    return out_cols


def closest(lst, c):
    return lst[min(range(len(lst)), key=lambda i: abs(lst[i] - c))]


def download_file(url, local_path=None):
    if local_path is None:
        local_path = url.split("/")[-1]
    r = requests.get(url)
    with open(local_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=512 * 1024):
            if chunk:  # filter out keep-alive new chunks
                f.write(chunk)
