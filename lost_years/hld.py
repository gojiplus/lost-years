"""HLD (Human Life-Table Database) module for lost_years package.

The pooled HLD file is a collection of life tables *as they were published*,
not one estimate per country-year: a single country-year is often covered by
several tables that differ in geography (whole country vs. a province),
sub-population (urban/rural, ethnicity, education), source publication, table
type and reference period. Choosing a row therefore needs an explicit,
documented rule; :func:`select_life_expectancy` is that rule.
"""

import argparse
import functools
import logging
import sys
from typing import Any

import pandas as pd
import pyarrow.parquet as pq

from .datasets import TableUnavailableError, resolve
from .utils import column_exists, fixup_columns

# Setup logger
logger = logging.getLogger(__name__)

# HLD is not shipped: lifetable.de asks that users download their own copy.
# `lost_years update --source hld` fetches it and writes this file.
HLD_FILENAME = "hld.parquet"

# Codebook fields that identify a sub-population. "0" means whole country /
# total population in every one of them (HLD formats.pdf, section 3.1).
CODE_COLS = ["region", "residence", "ethnicity", "socdem"]

NATIONAL_CODE = "0"

# A life table is quarantined when HLD's recalculated e(x) and the e(x) printed
# in the original publication differ by more than this many years anywhere in
# the table. The two columns are independent computations of the same quantity,
# so a large gap means at least one is wrong and neither can be trusted. It is
# the check that catches ARG 1980 (Ref-ID 1042.01), whose recalculated e(0) of
# 79.11 contradicts its own published 65.48.
DEFAULT_MAX_EX_DISCREPANCY = 2.0

# AgeInt sentinel for the open-ended top age interval.
OPEN_AGE_INTERVAL = 99

# Identifies one life table: everything except the age and the values.
TABLE_KEY = [
    "country",
    "region",
    "residence",
    "ethnicity",
    "socdem",
    "version",
    "ref_id",
    "year1",
    "year2",
    "type_lt",
    "sex",
]

SEX_TOKENS = {
    "m": "M",
    "male": "M",
    "1": "M",
    "f": "F",
    "female": "F",
    "2": "F",
}

OUTPUT_COLS = [
    "hld_country",
    "hld_sex",
    "hld_year1",
    "hld_year2",
    "hld_age",
    "hld_age_interval",
    "hld_life_expectancy",
    "hld_ref_id",
    "hld_version",
    "hld_type_lt",
    "hld_ex_discrepancy",
    "hld_n_candidates",
    "hld_match_status",
    "hld_region",
    "hld_residence",
    "hld_ethnicity",
    "hld_socdem",
]


@functools.lru_cache(maxsize=1)
def read_hld() -> pd.DataFrame:
    """Read the derived HLD table.

    The file is built by ``lost_years update --source hld``, which is where the
    upstream repairs live: sub-population codes read as text, HLD's literal
    ``NA`` region mapped to the whole-country code, and each life table's own
    largest ``|e(x) - e(x)Orig|`` precomputed into ``ex_discrepancy``. Reading
    is therefore a plain load with no cleaning, and the manifest beside the
    file says which upstream release it came from.

    Returns:
        Every HLD row eligible to be looked up, one per age interval of one
        published life table.
    """
    path = resolve("hld", HLD_FILENAME)
    logger.info("Reading HLD table from %s", path)
    return pq.read_table(path).to_pandas()


def eligible_tables(
    table: pd.DataFrame,
    national_only: bool = True,
    max_ex_discrepancy: float | None = DEFAULT_MAX_EX_DISCREPANCY,
) -> pd.DataFrame:
    """Keep only the HLD life tables that are allowed to answer a lookup.

    Three filters run before any query is answered:

    1. ``Region == Residence == Ethnicity == SocDem == '0'`` keeps the
       whole-country total population. Skipped when ``national_only`` is False.
    2. ``TypeLT == 2`` is dropped. Type 2 is HLD's own abridgement of the type 1
       complete table from the same source, so it never carries information the
       finer table does not already have.
    3. Tables whose recalculated and published life expectancies disagree by
       more than ``max_ex_discrepancy`` years are quarantined.

    Args:
        table: Every HLD row, as returned by :func:`read_hld`.
        national_only: Keep only whole-country, total-population life tables.
        max_ex_discrepancy: Quarantine threshold in years. None serves the
            quarantined tables anyway.

    Returns:
        The eligible subset.
    """
    if national_only:
        mask = table[CODE_COLS[0]] == NATIONAL_CODE
        for col in CODE_COLS[1:]:
            mask &= table[col] == NATIONAL_CODE
        table = table[mask]
    table = table[table["type_lt"] != 2]
    if max_ex_discrepancy is not None:
        table = table[~(table["ex_discrepancy"] > max_ex_discrepancy)]
    return table


@functools.lru_cache(maxsize=4)
def load_hld_table(
    national_only: bool = True,
    max_ex_discrepancy: float | None = DEFAULT_MAX_EX_DISCREPANCY,
) -> pd.DataFrame:
    """Load the HLD life tables that are eligible to answer a lookup.

    The result is cached, so repeated calls with the same arguments neither
    re-read nor re-filter the 2.2M-row table.

    Args:
        national_only: Keep only whole-country, total-population life tables.
        max_ex_discrepancy: Quarantine threshold in years. None serves the
            quarantined tables anyway.

    Returns:
        The eligible subset of the HLD table.
    """
    table = read_hld()
    logger.info(
        "Loaded HLD data: %d rows, %d countries",
        len(table),
        table["country"].nunique(),
    )
    table = eligible_tables(table, national_only, max_ex_discrepancy)
    logger.info("Eligible HLD rows after filtering: %d", len(table))
    return table


def empty_result(status: str) -> dict[str, Any]:
    """Build an all-missing output record.

    Args:
        status: Why no life expectancy could be returned.

    Returns:
        Mapping of output column name to value.
    """
    record: dict[str, Any] = dict.fromkeys(OUTPUT_COLS)
    record["hld_match_status"] = status
    return record


def select_life_expectancy(
    table: pd.DataFrame,
    country: str,
    year: float,
    sex: str,
    age: float,
    year_tolerance: float | None = None,
) -> dict[str, Any]:
    """Pick exactly one HLD row for one (country, year, sex, age) query.

    The rule, in order:

    1. **Country**: exact ISO-3166-1 alpha-3 match, case-insensitive. No
       substring or regular-expression matching -- ``US`` is not a country code
       and must not match ``AUS``.
    2. **Period containment**: keep tables with ``Year1 <= year <= Year2``.
       2,482 country-years in HLD are reachable only through a multi-year
       period table, so containment is required, not optional. A year no table
       covers returns nothing unless ``year_tolerance`` is set, in which case
       the nearest period within the tolerance is used and
       ``hld_match_status`` records the distance.
    3. **Narrowest period**: of those, keep the tables with the smallest
       ``Year2 - Year1``, so a 1980 table beats a 1976-1980 table for 1980.
    4. **Age interval**: keep the row whose interval ``[Age, Age + AgeInt)``
       contains the requested age. ``AgeInt == 99`` marks the open top interval;
       the 37 upstream rows with a negative ``AgeInt`` cannot define an interval
       and are dropped.
    5. **Tie-break convention**: highest ``Version``, then highest ``Ref-ID``,
       then latest ``Year1``, then lowest ``TypeLT``. Version is HLD's own
       revision counter, so the highest is the most revised table; Ref-ID rises
       as sources are added, so the highest is the most recently added source.
       The last two keys exist only to make the order total. About 17% of
       country-year cells still reach this step with more than one candidate,
       which is why the count is reported in ``hld_n_candidates`` rather than
       hidden.

    Args:
        table: Eligible HLD rows, as returned by :func:`load_hld_table`.
        country: ISO-3166-1 alpha-3 country code.
        year: Calendar year.
        sex: "M" or "F".
        age: Exact age in years.
        year_tolerance: How many years outside a table's period the query may
            fall before the table stops being an acceptable answer. None, the
            default, requires containment.

    Returns:
        Mapping of output column name to value. ``hld_match_status`` is "ok"
        when a row was selected and says what went wrong otherwise.
    """
    if sex not in ("M", "F"):
        return empty_result("unrecognised sex")
    if pd.isna(year):
        return empty_result("missing year")
    if pd.isna(age):
        return empty_result("missing age")

    rows = table[(table["country"] == country) & (table["sex"] == sex)]
    if rows.empty:
        return empty_result("no eligible life table for country")

    # Years before Year1 and after Year2 are both outside the period; a covered
    # year has distance 0.
    distance = (rows["year1"] - year).clip(lower=0) + (year - rows["year2"]).clip(
        lower=0
    )
    limit = 0 if year_tolerance is None else year_tolerance
    rows = rows[distance <= limit]
    if rows.empty:
        return empty_result("no eligible life table covering year")
    gap = int(distance[rows.index].min())
    rows = rows[distance[rows.index] == gap]

    span = rows["year2"] - rows["year1"]
    rows = rows[span == span.min()]

    interval = rows["age_interval"]
    upper = rows["age"] + interval.where(interval != OPEN_AGE_INTERVAL, float("inf"))
    rows = rows[(interval > 0) & (rows["age"] <= age) & (upper > age)]
    if rows.empty:
        return empty_result("no age interval covering age")

    n_candidates = len(rows)
    best = rows.sort_values(
        ["version", "ref_id_sort", "year1", "type_lt"],
        ascending=[False, False, False, True],
    ).iloc[0]
    status = "ok" if gap == 0 else f"ok: nearest period, {gap} year(s) away"

    return {
        "hld_country": best["country"],
        "hld_sex": best["sex"],
        "hld_year1": int(best["year1"]),
        "hld_year2": int(best["year2"]),
        "hld_age": int(best["age"]),
        "hld_age_interval": int(best["age_interval"]),
        "hld_life_expectancy": float(best["life_expectancy"]),
        "hld_ref_id": best["ref_id"],
        "hld_version": int(best["version"]),
        "hld_type_lt": int(best["type_lt"]),
        "hld_ex_discrepancy": float(best["ex_discrepancy"]),
        "hld_n_candidates": n_candidates,
        "hld_match_status": status,
        "hld_region": best["region"],
        "hld_residence": best["residence"],
        "hld_ethnicity": best["ethnicity"],
        "hld_socdem": best["socdem"],
    }


def select_subpopulations(
    table: pd.DataFrame,
    country: str,
    year: float,
    sex: str,
    age: float,
    year_tolerance: float | None = None,
) -> list[dict[str, Any]]:
    """Run :func:`select_life_expectancy` once per available sub-population.

    Each sub-population is resolved on its own, so every returned row is as
    unambiguous as the national-total row is by default; what varies is how
    many rows come back.

    Args:
        table: Eligible HLD rows including sub-populations.
        country: ISO-3166-1 alpha-3 country code.
        year: Calendar year.
        sex: "M" or "F".
        age: Exact age in years.
        year_tolerance: Passed through to :func:`select_life_expectancy`.

    Returns:
        One record per sub-population with a life table for this query, or a
        single all-missing record when there is none.
    """
    rows = table[table["country"] == country]
    records = []
    # observed=True: the code columns are dictionary-encoded, so the default
    # would enumerate every code seen anywhere in HLD for every country.
    for _, group in rows.groupby(CODE_COLS, sort=True, observed=True):
        record = select_life_expectancy(
            group, country, year, sex, age, year_tolerance=year_tolerance
        )
        if record["hld_match_status"].startswith("ok"):
            records.append(record)
    if not records:
        return [empty_result("no eligible life table for country")]
    return records


def normalise_sex(value: Any) -> str:
    """Map an input sex value onto "M" or "F".

    Args:
        value: Raw value from the input DataFrame.

    Returns:
        "M", "F", or "" when the value is not a recognised token.
    """
    return SEX_TOKENS.get(str(value).strip().lower(), "")


class LostYearsHLDData:
    """HLD data handler for life table information."""

    @classmethod
    def lost_years_hld(
        cls,
        df: pd.DataFrame,
        cols: dict[str, str] | None = None,
        subpopulations: bool = False,
        max_ex_discrepancy: float | None = DEFAULT_MAX_EX_DISCREPANCY,
        year_tolerance: float | None = None,
    ) -> pd.DataFrame:
        """Append HLD life expectancy to the input DataFrame.

        Every input row gets exactly one output row by default, taken from the
        whole-country total-population life table chosen by
        :func:`select_life_expectancy`. ``hld_match_status`` says why a lookup
        returned nothing, and ``hld_n_candidates`` says how many equally
        eligible life tables the tie-break had to choose between.

        Args:
            df: Pandas DataFrame containing the input data.
            cols: Column mapping for country, age, sex, and year in DataFrame.
                None for default mapping: {'country': 'country', 'age': 'age',
                'sex': 'sex', 'year': 'year'}.
            subpopulations: Emit one row per available sub-population (region,
                urban/rural, ethnicity, socio-demographic group) instead of the
                single national total. The output then has more rows than the
                input.
            max_ex_discrepancy: Quarantine threshold in years for the gap
                between HLD's recalculated and published life expectancy. None
                serves the quarantined life tables anyway.
            year_tolerance: How many years outside a life table's period a
                query may fall before the table stops being an acceptable
                answer. None, the default, requires the period to contain the
                requested year; setting it records the distance in
                ``hld_match_status``.

        Returns:
            The input DataFrame with the HLD columns appended.

        Note:
            Propagates :class:`lost_years.TableUnavailableError` when no HLD
            table has been downloaded yet. HLD is not shipped in the wheel; run
            ``lost_years update --source hld`` once to install it.
        """
        df_cols = {}
        for col in ["country", "age", "sex", "year"]:
            tcol = col if cols is None else cols[col]
            if tcol not in df.columns:
                logger.warning("No column `%s` in the DataFrame", tcol)
                return df
            df_cols[col] = tcol

        table = load_hld_table(
            national_only=not subpopulations,
            max_ex_discrepancy=max_ex_discrepancy,
        )

        records: list[dict[str, Any]] = []
        positions: list[int] = []
        for position, (_, row) in enumerate(df.iterrows()):
            country = str(row[df_cols["country"]]).strip().upper()
            sex = normalise_sex(row[df_cols["sex"]])
            year = pd.to_numeric(row[df_cols["year"]], errors="coerce")
            age = pd.to_numeric(row[df_cols["age"]], errors="coerce")
            args = (table, country, year, sex, age)
            found = (
                select_subpopulations(*args, year_tolerance=year_tolerance)
                if subpopulations
                else [select_life_expectancy(*args, year_tolerance=year_tolerance)]
            )
            records.extend(found)
            positions.extend([position] * len(found))

        result = df.iloc[positions].copy()
        appended = pd.DataFrame(records, columns=OUTPUT_COLS)
        for col in OUTPUT_COLS:
            result[col] = appended[col].to_numpy()
        return result


# Export the function
lost_years_hld = LostYearsHLDData.lost_years_hld


def main(argv: list[str] = sys.argv[1:]) -> int:
    """Run the ``lost_years_hld`` command line interface.

    Args:
        argv: Command line arguments, defaulting to the process arguments.

    Returns:
        0 on success, -1 when a required column is missing or no HLD table has
        been installed.
    """
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
        "--subpopulations",
        action="store_true",
        help="Emit one row per sub-population instead of the national total",
    )
    parser.add_argument(
        "--no-quarantine",
        action="store_true",
        help="Serve life tables whose recalculated and published e(x) disagree",
    )
    parser.add_argument(
        "--year-tolerance",
        type=float,
        default=None,
        help="Accept a life table whose period misses the year by this much",
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
    for col_arg in (args.country, args.age, args.sex, args.year):
        if not column_exists(df, col_arg):
            logger.error("Column: `%s` not found in the input file", col_arg)
            return -1

    # Apply HLD lookup
    try:
        result_df = lost_years_hld(
            df,
            cols={
                "country": args.country,
                "age": args.age,
                "sex": args.sex,
                "year": args.year,
            },
            subpopulations=args.subpopulations,
            max_ex_discrepancy=(
                None if args.no_quarantine else DEFAULT_MAX_EX_DISCREPANCY
            ),
            year_tolerance=args.year_tolerance,
        )
    except TableUnavailableError as exc:
        logger.error("%s", exc)
        return -1

    # Save output
    logger.info("Saving output to file: `%s`", args.output)
    result_df.columns = fixup_columns(result_df.columns.tolist())
    result_df.to_csv(args.output, index=False)

    return 0


if __name__ == "__main__":
    sys.exit(main())
