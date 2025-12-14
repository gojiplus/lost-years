#!/usr/bin/env python

import argparse
import sys
from importlib.resources import files

import pandas as pd

from .utils import closest, column_exists, fixup_columns

SSA_DATA = files("lost_years") / "data" / "ssa" / "ssa.csv"
SSA_COLS = ["age", "male_life_expectancy", "female_life_expectancy", "year"]


class LostYearsSSAData:
    __df = None

    @classmethod
    def lost_years_ssa(cls, df: pd.DataFrame, cols: dict[str, str] | None = None) -> pd.DataFrame:
        """Appends Life expectancycolumn from SSA data to the input DataFrame
        based on age, sex and year in the specific cols mapping

        Args:
            df: Pandas DataFrame containing the input data.
            cols: Column mapping for age, sex, and year in DataFrame.
                If None, uses default mapping: {'age': 'age', 'sex': 'sex', 'year': 'year'}

        Returns:
            Pandas DataFrame with life expectancy columns:
                'ssa_age', 'ssa_year', 'ssa_life_expectancy'
        """
        df_cols = {}
        for col in ["age", "sex", "year"]:
            tcol = col if cols is None else cols[col]
            if tcol not in df.columns:
                print(f"No column `{tcol!s}` in the DataFrame")
                return df
            df_cols[col] = tcol

        if cls.__df is None:
            cls.__df = pd.read_csv(str(SSA_DATA), usecols=SSA_COLS)

        out_df = pd.DataFrame()
        for i, r in df.iterrows():
            if r[df_cols["sex"]].lower() in ["m", "male"]:
                ecol = "male_life_expectancy"
            else:
                ecol = "female_life_expectancy"
            sdf = cls.__df[["age", "year", ecol]]
            for c in ["age", "year"]:
                sdf = sdf[sdf[c] == closest(sdf[c].unique(), r[df_cols[c]])]
            odf = sdf[["age", "year", ecol]].copy()
            odf.columns = ["ssa_age", "ssa_year", "ssa_life_expectancy"]
            odf["index"] = i
            out_df = pd.concat([out_df, odf])
        out_df.set_index("index", drop=True, inplace=True)
        rdf = df.join(out_df)
        return rdf


lost_years_ssa = LostYearsSSAData.lost_years_ssa


def main(argv: list[str] = sys.argv[1:]) -> int:
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

    print(args)

    df = pd.read_csv(args.input)

    if not column_exists(df, args.age):
        print(f"Column: `{args.age!s}` not found in the input file")
        return -1

    if not column_exists(df, args.sex):
        print(f"Column: `{args.sex!s}` not found in the input file")
        return -1

    if not column_exists(df, args.year):
        print(f"Column: `{args.year!s}` not found in the input file")
        return -1

    rdf = lost_years_ssa(df, cols={"age": args.age, "sex": args.sex, "year": args.year})

    print(f"Saving output to file: `{args.output:s}`")
    rdf.columns = fixup_columns(rdf.columns)  # type: ignore[arg-type]
    rdf.to_csv(args.output, index=False)

    return 0


if __name__ == "__main__":
    sys.exit(main())
