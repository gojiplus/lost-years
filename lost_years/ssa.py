"""SSA (US Social Security Administration) period life tables for lost_years."""

import argparse
import logging
import sys
from importlib.resources import files

import pandas as pd

from .utils import closest, column_exists, fixup_columns

# Setup logger
logger = logging.getLogger(__name__)

SSA_DATA = files("lost_years") / "data" / "ssa" / "ssa.csv"
SSA_COLS = ["age", "male_life_expectancy", "female_life_expectancy", "year"]


class LostYearsSSAData:
    """SSA life-table lookup, caching the packaged table on first use."""

    __df = None

    @classmethod
    def lost_years_ssa(
        cls, df: pd.DataFrame, cols: dict[str, str] | None = None
    ) -> pd.DataFrame:
        """Append SSA life expectancy to the input DataFrame.

        Matches each row on age, sex and year using the column names given by
        ``cols``.

        Args:
            df: Pandas DataFrame containing the input data.
            cols: Column mapping for age, sex, and year in DataFrame. If None,
                uses the default mapping
                ``{'age': 'age', 'sex': 'sex', 'year': 'year'}``.

        Returns:
            Pandas DataFrame with life expectancy columns:
                'ssa_age', 'ssa_year', 'ssa_life_expectancy'
        """
        df_cols = {}
        for col in ["age", "sex", "year"]:
            tcol = col if cols is None else cols[col]
            if tcol not in df.columns:
                logger.warning("No column `%s` in the DataFrame", tcol)
                return df
            df_cols[col] = tcol

        if cls.__df is None:
            cls.__df = pd.read_csv(str(SSA_DATA), usecols=SSA_COLS)

        out_list = []
        index_list = []
        for i, r in df.iterrows():
            if r[df_cols["sex"]].lower() in ["m", "male"]:
                ecol = "male_life_expectancy"
            else:
                ecol = "female_life_expectancy"
            sdf = cls.__df[["age", "year", ecol]]
            for c in ["age", "year"]:
                sdf = sdf[sdf[c] == closest(sdf[c].unique(), r[df_cols[c]])]
            if not sdf.empty:
                odf = sdf[["age", "year", ecol]].copy()
                odf.columns = ["ssa_age", "ssa_year", "ssa_life_expectancy"]
                out_list.append(odf)
                index_list.append(i)

        if out_list:
            out_df = pd.concat(out_list, ignore_index=True)
            out_df["original_index"] = index_list
            out_df.set_index("original_index", drop=True, inplace=True)
        else:
            out_df = pd.DataFrame()
        return df.join(out_df)


lost_years_ssa = LostYearsSSAData.lost_years_ssa


def main(argv: list[str] = sys.argv[1:]) -> int:
    """Run the ``lost_years_ssa`` command line interface.

    Args:
        argv: Command line arguments, defaulting to the process arguments.

    Returns:
        0 on success, -1 when a required column is missing.
    """
    title = "Appends Lost Years data column(s) by age, sex and year"
    parser = argparse.ArgumentParser(description=title)
    parser.add_argument("input", default=None, help="Input file")
    parser.add_argument(
        "-a",
        "--age",
        default="age",
        help="Columns name of age in the input file(default=`age`)",
    )
    parser.add_argument(
        "-s",
        "--sex",
        default="sex",
        help="Columns name of sex in the input file(default=`sex`)",
    )
    parser.add_argument(
        "-y",
        "--year",
        default="year",
        help="Columns name of year in the input file(default=`year`)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="lost-years-output.csv",
        help="Output file with Lost Years data column(s)",
    )

    args = parser.parse_args(argv)

    logger.debug(args)

    df = pd.read_csv(args.input)

    if not column_exists(df, args.age):
        logger.error("Column: `%s` not found in the input file", args.age)
        return -1

    if not column_exists(df, args.sex):
        logger.error("Column: `%s` not found in the input file", args.sex)
        return -1

    if not column_exists(df, args.year):
        logger.error("Column: `%s` not found in the input file", args.year)
        return -1

    rdf = lost_years_ssa(df, cols={"age": args.age, "sex": args.sex, "year": args.year})

    logger.info("Saving output to file: `%s`", args.output)
    rdf.columns = fixup_columns(rdf.columns)  # type: ignore[arg-type]
    rdf.to_csv(args.output, index=False)

    return 0


if __name__ == "__main__":
    sys.exit(main())
