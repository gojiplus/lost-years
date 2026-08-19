"""WHO (World Health Organization) life expectancy tables for lost_years.

The packaged WHO table is indicator WHOSIS_000001, *life expectancy at birth*.
It has no age dimension: one value per country, year and sex. The lookup
therefore answers questions about age 0 only, and says so in the name of the
column it returns. Asking it for remaining life expectancy at a given age is a
question it cannot answer, so an explicit ``age`` mapping raises instead of
being quietly ignored; use :func:`lost_years.lost_years_hld` for that.
"""

import argparse
import logging
import re
import sys
from typing import Any

import pandas as pd
import pyarrow.parquet as pq

from .datasets import TableUnavailableError, resolve
from .utils import closest, column_exists, fixup_columns

# Setup logger
logger = logging.getLogger(__name__)

# Not shipped: a packaged copy is stale the day WHO publishes a revision and
# nothing in the wheel would say so. `lost_years update --source who` fetches it.
WHO_FILENAME = "who.parquet"

# Same policy as SSA: report the matched year rather than refuse. See ssa.py.
WHO_YEAR_TOLERANCE = None

WHO_OUTPUT_COLS = [
    "who_country",
    "who_sex",
    "who_year",
    "who_life_expectancy_at_birth",
    "who_match_status",
]


class LostYearsWHOData:
    """WHO life-table lookup, caching the packaged table on first use."""

    __df = None
    # A cache filled at runtime, not a default shared between instances: every
    # access goes through the class, so RUF012's ClassVar advice does not apply.
    __who_trans: dict[str, str] = {}  # noqa: RUF012

    @classmethod
    def lost_years_who(
        cls,
        df: pd.DataFrame,
        cols: dict[str, str] | None = None,
        year_tolerance: float | None = WHO_YEAR_TOLERANCE,
    ) -> pd.DataFrame:
        """Append WHO life expectancy at birth to the input DataFrame.

        Matches each row on country, sex and year using the column names given
        by ``cols``. There is deliberately no age dimension: the packaged WHO
        indicator is life expectancy *at birth*, so the returned column is
        named for what it holds and an ``age`` mapping is refused.

        Args:
            df: Pandas DataFrame containing the input data.
            cols: Column mapping for country, sex, and year in DataFrame.
                None for default mapping: {'country': 'country',
                'sex': 'sex', 'year': 'year'}.
            year_tolerance: How far, in calendar years, the match may sit from
                the requested year. None accepts any distance.

        Returns:
            Pandas DataFrame with WHO data columns:
                'who_country', 'who_sex', 'who_year',
                'who_life_expectancy_at_birth', 'who_match_status'.

        Raises:
            ValueError: If ``cols`` maps an ``age`` column. The WHO table
                cannot answer an age-specific question.

        Note:
            Propagates :class:`lost_years.TableUnavailableError` when no WHO
            table has been downloaded yet; run ``lost_years update --source
            who`` once to install it.
        """
        if cols is not None and "age" in cols:
            raise ValueError(
                "the packaged WHO table is life expectancy at birth and has no "
                "age dimension; drop the 'age' mapping, or use lost_years_hld "
                "for remaining life expectancy at a given age"
            )

        df_cols = {}
        for col in ["country", "sex", "year"]:
            tcol = col if cols is None else cols[col]
            if tcol not in df.columns:
                logger.warning("No column `%s` in the DataFrame", tcol)
                return df
            df_cols[col] = tcol

        if cls.__df is None:
            cls.__df = (
                pq.read_table(resolve("who", WHO_FILENAME))
                .to_pandas()
                .rename(columns={"country_code": "country", "sex_code": "sex"})
            )

        years = cls.__df["year"].unique()
        records = []
        for _, r in df.iterrows():
            sex_in = str(r[df_cols["sex"]]).strip().lower()
            sex = "MLE" if sex_in in ("m", "male", "mle", "1") else "FMLE"
            country = str(r[df_cols["country"]]).strip().upper()
            try:
                year = closest(years, r[df_cols["year"]], tolerance=year_tolerance)
            except ValueError as exc:
                logger.warning("No WHO match: %s", exc)
                records.append(cls.__no_match(str(exc)))
                continue
            sdf = cls.__df[
                (cls.__df["country"].str.upper() == country)
                & (cls.__df["sex"] == sex)
                & (cls.__df["year"] == year)
            ]
            if sdf.empty:
                records.append(cls.__no_match("no WHO row for country, sex and year"))
                continue
            best = sdf.iloc[0]
            records.append(
                {
                    "who_country": best["country"],
                    "who_sex": best["sex"],
                    "who_year": int(best["year"]),
                    "who_life_expectancy_at_birth": float(best["life_expectancy"]),
                    "who_match_status": "ok",
                }
            )

        result = df.copy()
        appended = pd.DataFrame(records, columns=WHO_OUTPUT_COLS)
        for col in WHO_OUTPUT_COLS:
            result[col] = appended[col].to_numpy() if records else None
        return result

    @classmethod
    def __no_match(cls, status: str) -> dict[str, Any]:
        """Build an all-missing WHO output record.

        Args:
            status: Why no life expectancy could be returned.

        Returns:
            Mapping of output column name to value.
        """
        record: dict[str, Any] = dict.fromkeys(WHO_OUTPUT_COLS)
        record["who_match_status"] = status
        return record

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
        0 on success, -1 when a required column is missing or no WHO table has
        been installed.
    """
    title = "Appends WHO life expectancy at birth by country, sex and year"
    parser = argparse.ArgumentParser(description=title)
    parser.add_argument("input", default=None, help="Input file")
    parser.add_argument(
        "-c",
        "--country",
        default="country",
        help="Columns name of country in the input file(default=`country`)",
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

    for col_arg in (args.country, args.sex, args.year):
        if not column_exists(df, col_arg):
            logger.error("Column: `%s` not found in the input file", col_arg)
            return -1

    try:
        rdf = lost_years_who(
            df,
            cols={
                "country": args.country,
                "sex": args.sex,
                "year": args.year,
            },
        )
    except TableUnavailableError as exc:
        logger.error("%s", exc)
        return -1

    logger.info("Saving output to file: `%s`", args.output)
    rdf.columns = fixup_columns(rdf.columns)  # type: ignore[arg-type]
    rdf.to_csv(args.output, index=False)

    return 0


if __name__ == "__main__":
    sys.exit(main())
