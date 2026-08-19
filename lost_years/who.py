"""WHO (World Health Organization) life expectancy tables for lost_years."""

import argparse
import logging
import re
import sys
from importlib.resources import files

import pandas as pd

from .utils import closest, column_exists, fixup_columns

# Setup logger
logger = logging.getLogger(__name__)

WHO_DATA = files("lost_years") / "data" / "who" / "who.csv.gz"
WHO_COLS = ["country_code", "year", "sex_code", "life_expectancy", "low_ci", "high_ci"]


class LostYearsWHOData:
    """WHO life-table lookup, caching the packaged table on first use."""

    __df = None
    # A cache filled at runtime, not a default shared between instances: every
    # access goes through the class, so RUF012's ClassVar advice does not apply.
    __who_trans: dict[str, str] = {}  # noqa: RUF012

    @classmethod
    def lost_years_who(
        cls, df: pd.DataFrame, cols: dict[str, str] | None = None
    ) -> pd.DataFrame:
        """Append WHO life expectancy to the input DataFrame.

        Matches each row on country, age, sex and year using the column names
        given by ``cols``.

        Args:
            df: Pandas DataFrame containing the input data.
            cols: Column mapping for country, age, sex, and year in DataFrame.
                None for default mapping: {'country': 'country', 'age': 'age',
                'sex': 'sex', 'year': 'year'}.

        Returns:
            Pandas DataFrame with WHO data columns:
                'who_country', 'who_age', 'who_sex', 'who_year', ...
        """
        df_cols = {}
        for col in ["country", "age", "sex", "year"]:
            tcol = col if cols is None else cols[col]
            if tcol not in df.columns:
                logger.warning("No column `%s` in the DataFrame", tcol)
                return df
            df_cols[col] = tcol

        if cls.__df is None:
            cls.__df = pd.read_csv(str(WHO_DATA), compression="gzip")
            # Data is already clean with schema-compliant columns
            # Add age column (WHO data is life expectancy at birth)
            cls.__df["age"] = 1  # Life expectancy at birth maps to age 1 for lookup
            # Rename for consistency with existing interface
            cls.__df = cls.__df.rename(
                columns={"country_code": "country", "sex_code": "sex"}
            )

        # Create a working copy to avoid modifying the original DataFrame
        df_work = df.copy()

        # Create normalized sex column for lookup
        df_work["__normalized_sex"] = df_work[df_cols["sex"]].apply(
            lambda c: "MLE" if c.lower() in ["m", "male", "mle"] else "FMLE"
        )

        out_df = pd.DataFrame()
        for i, r in df_work.iterrows():
            sdf = cls.__df
            for c in ["country", "age", "year"]:
                if sdf[c].dtype in ["int32", "int64", "float64"]:
                    sdf = sdf[sdf[c] == closest(sdf[c].unique(), r[df_cols[c]])]
                else:
                    sdf = sdf[sdf[c].str.lower() == r[df_cols[c]].lower()]
            # Handle sex column separately using normalized value
            sdf = sdf[sdf["sex"].str.lower() == r["__normalized_sex"].lower()]

            # Select relevant columns and rename for output
            odf = sdf[["age", "country", "sex", "year", "life_expectancy"]].copy()
            odf["index"] = i  # type: ignore[call-overload]
            out_df = pd.concat([out_df, odf])
        out_df.set_index("index", drop=True, inplace=True)
        out_df.columns = ["who_" + c for c in out_df.columns]
        return df.join(out_df)

    @classmethod
    def convert_agegroup(cls, ag: str) -> int:
        """Convert a WHO age-group code to the lower bound of its range.

        Args:
            ag: WHO age group code, e.g. ``AGE45-49`` or ``AGE85PLUS``.

        Returns:
            The lowest age in the group, or 0 when the code is unrecognised.
        """
        if ag == "AGE100+":
            return 100
        if ag == "AGE85PLUS":
            return 85
        if ag == "AGELT1":
            return 1
        m = re.match(r"AGE(\d+)\-(\d+)", ag)
        if m:
            return int(m.group(1))
        return 0


lost_years_who = LostYearsWHOData.lost_years_who


def main(argv: list[str] = sys.argv[1:]) -> int:
    """Run the ``lost_years_who`` command line interface.

    Args:
        argv: Command line arguments, defaulting to the process arguments.

    Returns:
        0 on success, -1 when a required column is missing.
    """
    title = "Appends Lost Years data column(s) by country, age, sex and year"
    parser = argparse.ArgumentParser(description=title)
    parser.add_argument("input", default=None, help="Input file")
    parser.add_argument(
        "-c",
        "--country",
        default="country",
        help="Columns name of country in the input file(default=`country`)",
    )
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

    if not column_exists(df, args.country):
        logger.error("Column: `%s` not found in the input file", args.country)
        return -1

    if not column_exists(df, args.age):
        logger.error("Column: `%s` not found in the input file", args.age)
        return -1

    if not column_exists(df, args.sex):
        logger.error("Column: `%s` not found in the input file", args.sex)
        return -1

    if not column_exists(df, args.year):
        logger.error("Column: `%s` not found in the input file", args.year)
        return -1

    rdf = lost_years_who(
        df,
        cols={
            "country": args.country,
            "age": args.age,
            "sex": args.sex,
            "year": args.year,
        },
    )

    logger.info("Saving output to file: `%s`", args.output)
    rdf.columns = fixup_columns(rdf.columns)  # type: ignore[arg-type]
    rdf.to_csv(args.output, index=False)

    return 0


if __name__ == "__main__":
    sys.exit(main())
