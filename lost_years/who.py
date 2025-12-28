#!/usr/bin/env python

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
    __df = None
    __who_trans: dict[str, str] = {}

    @classmethod
    def lost_years_who(cls, df: pd.DataFrame, cols: dict[str, str] | None = None) -> pd.DataFrame:
        """Appends Life expectancy column from WHO data to the input DataFrame
        based on country, age, sex and year in the specific cols mapping.

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
                logger.warning(f"No column `{tcol!s}` in the DataFrame")
                return df
            df_cols[col] = tcol

        if cls.__df is None:
            cls.__df = pd.read_csv(str(WHO_DATA), compression="gzip")
            # Data is already clean with schema-compliant columns
            # Add age column (WHO data is life expectancy at birth)
            cls.__df["age"] = 1  # Life expectancy at birth maps to age 1 for lookup
            # Rename for consistency with existing interface
            cls.__df = cls.__df.rename(columns={"country_code": "country", "sex_code": "sex"})

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
        rdf = df.join(out_df)

        return rdf

    @classmethod
    def convert_agegroup(cls, ag):
        if ag == "AGE100+":
            return 100
        if ag == "AGE85PLUS":
            return 85
        if ag == "AGELT1":
            return 1
        m = re.match(r"AGE(\d+)\-(\d+)", ag)
        if m:
            return int(m.group(1))
        else:
            return 0


lost_years_who = LostYearsWHOData.lost_years_who


def main(argv: list[str] = sys.argv[1:]) -> int:
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
        logger.error(f"Column: `{args.country!s}` not found in the input file")
        return -1

    if not column_exists(df, args.age):
        logger.error(f"Column: `{args.age!s}` not found in the input file")
        return -1

    if not column_exists(df, args.sex):
        logger.error(f"Column: `{args.sex!s}` not found in the input file")
        return -1

    if not column_exists(df, args.year):
        logger.error(f"Column: `{args.year!s}` not found in the input file")
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

    logger.info(f"Saving output to file: `{args.output:s}`")
    rdf.columns = fixup_columns(rdf.columns)  # type: ignore[arg-type]
    rdf.to_csv(args.output, index=False)

    return 0


if __name__ == "__main__":
    sys.exit(main())
