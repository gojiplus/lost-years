"""SSA (US Social Security Administration) period life tables for lost_years."""

import argparse
import logging
import sys

import pandas as pd
import pyarrow.parquet as pq

from .datasets import resolve
from .utils import closest, column_exists, fixup_columns

# Setup logger
logger = logging.getLogger(__name__)

# The one table that ships inside the wheel: a US federal work in the public
# domain, small enough that the package answers US questions offline. A copy
# installed by `lost_years update --source ssa` takes precedence over it.
SSA_FILENAME = "ssa.parquet"
SSA_COLS = ["age", "male_life_expectancy", "female_life_expectancy", "year"]

# The packaged table is complete on single years of age 0-119, so any age it
# covers matches exactly; the slack exists only to round a non-integer age.
SSA_AGE_TOLERANCE = 1.0

# No default limit on how far the matched year may sit from the requested one.
# The package's documented contract is closest-year matching, and `lost_years_ssa`
# is explicitly a counterfactual ("what if this person had had US life
# expectancy"), so a 2003 death answered from the 2022 table is the intent
# rather than an error. What was wrong before was doing it silently: the
# matched year and its distance are now always reported. Callers who want a
# hard limit pass `year_tolerance`.
SSA_YEAR_TOLERANCE = None

SSA_OUTPUT_COLS = ["ssa_age", "ssa_year", "ssa_life_expectancy", "ssa_match_status"]


def _match_status(
    *,
    requested_age: float,
    matched_age: float,
    requested_year: float,
    matched_year: float,
) -> str:
    """Describe how far the matched row sits from what was asked for.

    The table is a single calendar year, so an older query is answered from it
    by design (the counterfactual the package documents). Saying only "ok"
    would hide a two-decade gap, so the distance is spelled out.

    Args:
        requested_age: Age the caller asked for.
        matched_age: Age the lookup used.
        requested_year: Calendar year the caller asked for.
        matched_year: Calendar year the lookup used.

    Returns:
        "ok" for an exact match, otherwise a description of the gap.
    """
    notes = []
    if float(matched_age) != float(requested_age):
        notes.append(f"age {matched_age} for requested {requested_age}")
    if float(matched_year) != float(requested_year):
        gap = abs(float(matched_year) - float(requested_year))
        notes.append(
            f"table year {matched_year} for requested {requested_year} "
            f"({gap:.0f} years away)"
        )
    return "ok" if not notes else "ok: " + "; ".join(notes)


class LostYearsSSAData:
    """SSA life-table lookup, caching the packaged table on first use."""

    __df = None

    @classmethod
    def lost_years_ssa(
        cls,
        df: pd.DataFrame,
        cols: dict[str, str] | None = None,
        age_tolerance: float | None = SSA_AGE_TOLERANCE,
        year_tolerance: float | None = SSA_YEAR_TOLERANCE,
    ) -> pd.DataFrame:
        """Append SSA life expectancy to the input DataFrame.

        Matches each row on age, sex and year using the column names given by
        ``cols``. A row whose age or year lies further from the packaged table
        than the tolerances allow gets a missing life expectancy and a
        ``ssa_match_status`` saying so, rather than the nearest available
        figure passed off as the answer.

        Args:
            df: Pandas DataFrame containing the input data.
            cols: Column mapping for age, sex, and year in DataFrame. If None,
                uses the default mapping
                ``{'age': 'age', 'sex': 'sex', 'year': 'year'}``.
            age_tolerance: How far, in years of age, the match may sit from the
                requested age. None accepts any distance.
            year_tolerance: How far, in calendar years, the match may sit from
                the requested year. None accepts any distance.

        Returns:
            Pandas DataFrame with life expectancy columns:
                'ssa_age', 'ssa_year', 'ssa_life_expectancy', 'ssa_match_status'
        """
        df_cols = {}
        for col in ["age", "sex", "year"]:
            tcol = col if cols is None else cols[col]
            if tcol not in df.columns:
                logger.warning("No column `%s` in the DataFrame", tcol)
                return df
            df_cols[col] = tcol

        if cls.__df is None:
            cls.__df = pq.read_table(
                resolve("ssa", SSA_FILENAME), columns=SSA_COLS
            ).to_pandas()

        records = []
        for _, r in df.iterrows():
            sex = str(r[df_cols["sex"]]).strip().lower()
            ecol = (
                "male_life_expectancy"
                if sex in ("m", "male", "1")
                else "female_life_expectancy"
            )
            sdf = cls.__df[["age", "year", ecol]]
            try:
                age = closest(
                    sdf["age"].unique(), r[df_cols["age"]], tolerance=age_tolerance
                )
                year = closest(
                    sdf["year"].unique(), r[df_cols["year"]], tolerance=year_tolerance
                )
            except ValueError as exc:
                logger.warning("No SSA match: %s", exc)
                records.append(
                    {
                        "ssa_age": None,
                        "ssa_year": None,
                        "ssa_life_expectancy": None,
                        "ssa_match_status": str(exc),
                    }
                )
                continue
            match = sdf[(sdf["age"] == age) & (sdf["year"] == year)]
            records.append(
                {
                    "ssa_age": age,
                    "ssa_year": year,
                    "ssa_life_expectancy": float(match.iloc[0][ecol]),
                    "ssa_match_status": _match_status(
                        requested_age=r[df_cols["age"]],
                        matched_age=age,
                        requested_year=r[df_cols["year"]],
                        matched_year=year,
                    ),
                }
            )

        result = df.copy()
        appended = pd.DataFrame(records, columns=SSA_OUTPUT_COLS)
        for col in SSA_OUTPUT_COLS:
            result[col] = appended[col].to_numpy() if records else None
        return result


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
