#!/usr/bin/env python
"""
HLD (Human Life-Table Database) module for lost_years package.

Provides access to historical life table data from lifetable.de
covering 142 countries from 1751-2023.
"""

import argparse
import logging
import sys
from importlib.resources import files
from pathlib import Path

import pandas as pd

from .utils import closest, column_exists, fixup_columns

# Setup logger
logger = logging.getLogger(__name__)

# HLD Configuration
HLD_DATA = files("lost_years") / "data" / "hld" / "hld.csv.gz"
HLD_COLS = [
    "Country",
    "Year1",
    "Sex",
    "Age",
    "e(x)",
]  # Essential columns for life expectancy


class LostYearsHLDData:
    """HLD data handler for life table information."""

    __df = None

    @classmethod
    def lost_years_hld(cls, df: pd.DataFrame, cols: dict[str, str] | None = None) -> pd.DataFrame:
        """Appends Life expectancy column from HLD data to the input DataFrame
        based on country, age, sex and year in the specific cols mapping.

        Args:
            df: Pandas DataFrame containing the input data.
            cols: Column mapping for country, age, sex, and year in DataFrame.
                None for default mapping: {'country': 'country', 'age': 'age',
                'sex': 'sex', 'year': 'year'}.

        Returns:
            Pandas DataFrame with HLD data columns:
                'hld_country', 'hld_age', 'hld_sex', 'hld_year', 'hld_life_expectancy'.
        """
        df_cols = {}
        for col in ["country", "age", "sex", "year"]:
            tcol = col if cols is None else cols[col]
            if tcol not in df.columns:
                logger.warning(f"No column `{tcol!s}` in the DataFrame")
                return df
            df_cols[col] = tcol

        if cls.__df is None:
            # Check if HLD data file exists
            hld_path = Path(str(HLD_DATA))
            if not hld_path.exists():
                logger.error(f"HLD data file not found: {HLD_DATA}")
                logger.info("Run: python lost_years/data/hld/update_hld_data.py")
                logger.info("Or manually download from: https://www.lifetable.de/")
                return df

            try:
                # Load HLD data
                logger.info("Loading HLD data (this may take a moment for 2M+ records)...")
                cls.__df = pd.read_csv(
                    str(HLD_DATA), compression="gzip", usecols=HLD_COLS, low_memory=False
                )

                if cls.__df.empty:
                    logger.error("HLD data file is empty")
                    return df

                # Clean and standardize the data
                cls.__df = cls.__df.dropna(subset=["Country", "Year1", "Sex", "e(x)"])

                # Standardize column names for lookup
                cls.__df = cls.__df.rename(
                    columns={
                        "Country": "country",
                        "Year1": "year",
                        "Sex": "sex",
                        "Age": "age",
                        "e(x)": "life_expectancy",
                    }
                )

                # Convert sex codes: 1=Male, 2=Female -> M/F for consistency
                cls.__df["sex"] = cls.__df["sex"].map({1: "M", 2: "F"})

                # Convert data types
                cls.__df["year"] = pd.to_numeric(cls.__df["year"], errors="coerce")
                cls.__df["age"] = pd.to_numeric(cls.__df["age"], errors="coerce")
                cls.__df["life_expectancy"] = pd.to_numeric(
                    cls.__df["life_expectancy"], errors="coerce"
                )

                # Remove invalid records
                cls.__df = cls.__df.dropna()

                logger.info(f"Loaded HLD data: {len(cls.__df):,} records")
                logger.info(f"Countries: {cls.__df['country'].nunique()}")
                year_min = cls.__df["year"].min()
                year_max = cls.__df["year"].max()
                logger.info(f"Year range: {year_min:.0f}-{year_max:.0f}")

            except Exception as e:
                logger.error(f"Error loading HLD data: {e}")
                logger.error("The HLD data file may be corrupted or missing.")
                logger.info("Run: python lost_years/data/hld/update_hld_data.py")
                return df

        # Process input data
        # Convert sex to standard format
        df_temp = df.copy()
        df_temp["__temp_sex"] = df_temp[df_cols["sex"]].apply(
            lambda x: "M" if str(x).lower() in ["m", "male", "1"] else "F"
        )

        out_df = pd.DataFrame()
        for i, r in df_temp.iterrows():
            # Filter HLD data for this record
            sdf = cls.__df.copy()

            # Match country (try both exact and close matches)
            country_val = str(r[df_cols["country"]]).upper()
            country_matches = sdf[sdf["country"].str.upper() == country_val]

            if country_matches.empty:
                # Try partial matching for country codes
                country_matches = sdf[
                    sdf["country"].str.upper().str.contains(country_val, na=False)
                ]

            if country_matches.empty:
                # No country match found, skip this record
                empty_row = pd.DataFrame(
                    {
                        "hld_country": [None],
                        "hld_age": [None],
                        "hld_sex": [None],
                        "hld_year": [None],
                        "hld_life_expectancy": [None],
                        "index": [i],
                    }
                )
                out_df = pd.concat([out_df, empty_row])
                continue

            sdf = country_matches

            # Match other dimensions
            for c, col_name in [
                ("sex", "__temp_sex"),
                ("age", df_cols["age"]),
                ("year", df_cols["year"]),
            ]:
                if c == "sex":
                    target_val = r[col_name]
                else:
                    target_val = r[col_name]

                if sdf[c].dtype in ["int32", "int64", "float64"]:
                    # Numeric matching with closest value
                    sdf = sdf[sdf[c] == closest(sdf[c].unique(), target_val)]
                else:
                    # String matching
                    sdf = sdf[sdf[c].astype(str).str.upper() == str(target_val).upper()]

            # Get the best match
            if not sdf.empty:
                # If multiple matches, take the first one
                best_match = sdf.iloc[0]
                odf = pd.DataFrame(
                    {
                        "hld_country": [best_match["country"]],
                        "hld_age": [best_match["age"]],
                        "hld_sex": [best_match["sex"]],
                        "hld_year": [best_match["year"]],
                        "hld_life_expectancy": [best_match["life_expectancy"]],
                        "index": [i],
                    }
                )
            else:
                # No match found
                odf = pd.DataFrame(
                    {
                        "hld_country": [None],
                        "hld_age": [None],
                        "hld_sex": [None],
                        "hld_year": [None],
                        "hld_life_expectancy": [None],
                        "index": [i],
                    }
                )

            out_df = pd.concat([out_df, odf])

        # Clean up and join with original data
        out_df.set_index("index", drop=True, inplace=True)
        out_df = out_df.fillna("")  # Replace NaN with empty string for cleaner output

        # Join with original DataFrame
        result_df = df.join(out_df)
        return result_df


# Export the function
lost_years_hld = LostYearsHLDData.lost_years_hld


def main(argv: list[str] = sys.argv[1:]) -> int:
    """Main CLI function."""
    title = "Appends Lost Years data from HLD (Human Life-Table Database)"
    parser = argparse.ArgumentParser(description=title)
    parser.add_argument("input", default=None, help="Input file")
    parser.add_argument(
        "-c",
        "--country",
        default="country",
        help="Column name of country in the input file (default=`country`)",
    )
    parser.add_argument(
        "-a",
        "--age",
        default="age",
        help="Column name of age in the input file (default=`age`)",
    )
    parser.add_argument(
        "-s",
        "--sex",
        default="sex",
        help="Column name of sex in the input file (default=`sex`)",
    )
    parser.add_argument(
        "-y",
        "--year",
        default="year",
        help="Column name of year in the input file (default=`year`)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="lost-years-hld-output.csv",
        help="Output file with Lost Years HLD data",
    )

    args = parser.parse_args(argv)
    logger.debug(args)

    df = pd.read_csv(args.input)

    # Validate columns
    for _col_name, col_arg in [
        ("country", args.country),
        ("age", args.age),
        ("sex", args.sex),
        ("year", args.year),
    ]:
        if not column_exists(df, col_arg):
            logger.error(f"Column: `{col_arg!s}` not found in the input file")
            return -1

    # Apply HLD lookup
    result_df = lost_years_hld(
        df,
        cols={
            "country": args.country,
            "age": args.age,
            "sex": args.sex,
            "year": args.year,
        },
    )

    # Save output
    logger.info(f"Saving output to file: `{args.output:s}`")
    result_df.columns = fixup_columns(result_df.columns.tolist())
    result_df.to_csv(args.output, index=False)

    return 0


if __name__ == "__main__":
    sys.exit(main())
