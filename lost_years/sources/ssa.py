"""Fetch the SSA period life table and derive the shipped lookup table.

This is the one table the wheel ships. It is a US federal work in the public
domain and it is 10 KB, so the package answers US questions the moment it is
installed, with no download and no network.

The table is the Actuarial Life Table at
``ssa.gov/oact/STATS/table4c6.html``: one calendar year, single years of age
0-119, with the year and the Trustees Report it belongs to named in the page.

ssa.gov sits behind an edge that answers many automated clients with HTTP 403
regardless of headers, so ``lost_years update --source ssa`` may be refused on
some networks. When it is, the command says so and points at ``--from-file``:
save the page in a browser and build from that, which runs exactly the same
parse, validation and swap.
"""

import io
import logging
import re
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from ..datasets import ValidationError
from .base import Source

logger = logging.getLogger(__name__)

TABLE_URL = "https://www.ssa.gov/oact/STATS/table4c6.html"
HOME_URL = "https://www.ssa.gov/oact/STATS/table4c6.html"

# Exact age, then death probability / number of lives / life expectancy for
# each sex. SSA has published the table in this order since the series began.
COLUMNS = [
    "age",
    "male_death_prob",
    "male_n_lives",
    "male_life_expectancy",
    "female_death_prob",
    "female_n_lives",
    "female_life_expectancy",
]

# Single years of age 0-119.
EXPECTED_AGES = 120

# A period life table is a decreasing function of age with no reversals, and
# US life expectancy at birth has been inside this band for the whole series.
E0_BOUNDS = (60.0, 95.0)

# The page names its own year: "Period Life Table, 2022, as used in the 2025
# Trustees Report".
YEAR_IN_PAGE = re.compile(r"Period Life Table,?\s*(\d{4})")


class SSA(Source):
    """The US Social Security Administration period life table."""

    name = "ssa"
    title = "SSA period life table"
    home_url = HOME_URL
    download_url = TABLE_URL
    licence = "Public domain (work of the US federal government)"
    filename = "ssa.parquet"
    min_rows = EXPECTED_AGES
    ships_in_wheel = True

    def schema(self) -> pa.Schema:
        """Return the Arrow schema of the derived SSA table.

        Returns:
            The declared schema.
        """
        return pa.schema(
            [
                pa.field("age", pa.int16(), nullable=False),
                pa.field("male_death_prob", pa.float64(), nullable=False),
                pa.field("male_n_lives", pa.float64(), nullable=False),
                pa.field("male_life_expectancy", pa.float64(), nullable=False),
                pa.field("female_death_prob", pa.float64(), nullable=False),
                pa.field("female_n_lives", pa.float64(), nullable=False),
                pa.field("female_life_expectancy", pa.float64(), nullable=False),
                pa.field("year", pa.int16(), nullable=False),
            ]
        )

    def fetch(self, workdir: Path) -> Path:
        """Download the current Actuarial Life Table page.

        Args:
            workdir: Scratch directory to download into.

        Returns:
            Path to the downloaded HTML page.
        """
        target = workdir / "table4c6.html"
        target.write_text(self.get_text(TABLE_URL), encoding="utf-8")
        return target

    def upstream_release(self) -> str:
        """Report the table year ssa.gov is currently publishing.

        Returns:
            The year as a string.

        Raises:
            ValidationError: When the page does not name its year.
        """
        found = YEAR_IN_PAGE.search(self.get_text(TABLE_URL))
        if not found:
            raise ValidationError(f"ssa: {TABLE_URL} does not name a table year")
        return found.group(1)

    def release_of(self, raw: Path) -> str:
        """Read the table year out of a downloaded page or archived CSV.

        Args:
            raw: SSA HTML page, or a CSV carrying a ``year`` column.

        Returns:
            The year as a string.

        Raises:
            ValidationError: When the file names no year.
        """
        if raw.suffix.lower() == ".csv":
            return str(int(pd.read_csv(raw)["year"].iloc[0]))
        found = YEAR_IN_PAGE.search(raw.read_text(encoding="utf-8", errors="replace"))
        if not found:
            raise ValidationError(f"ssa: no table year found in {raw.name}")
        return found.group(1)

    def build(self, raw: Path, destination: Path) -> dict[str, Any]:
        """Derive the typed SSA table from a page or an archived CSV.

        Args:
            raw: SSA HTML page, or a CSV in the archived column layout.
            destination: Path to write the Parquet file to.

        Returns:
            Build notes for the manifest.
        """
        year = int(self.release_of(raw))
        table = (
            pd.read_csv(raw)[COLUMNS]
            if raw.suffix.lower() == ".csv"
            else self._parse_page(raw)
        )
        table = table.astype(dict.fromkeys(COLUMNS[1:], "float64"))
        table["age"] = table["age"].astype("int16")
        table["year"] = year
        table = table.sort_values("age", ignore_index=True)  # pyright: ignore[reportCallIssue]
        arrow = pa.Table.from_pandas(table, schema=self.schema(), preserve_index=False)
        pq.write_table(arrow, destination, compression="zstd", write_statistics=True)
        return {"table_year": year, "input_format": raw.suffix.lstrip(".") or "html"}

    @staticmethod
    def _parse_page(raw: Path) -> pd.DataFrame:
        """Pull the seven-column life table out of an SSA page.

        Args:
            raw: SSA HTML page.

        Returns:
            The table, with the documented column names.

        Raises:
            ValidationError: When the page carries no seven-column table with
                one row per single year of age.
        """
        text = raw.read_text(encoding="utf-8", errors="replace")
        for candidate in pd.read_html(io.StringIO(text)):
            numeric = candidate.apply(pd.to_numeric, errors="coerce").dropna(how="any")
            if numeric.shape[1] == len(COLUMNS) and len(numeric) >= EXPECTED_AGES:
                numeric.columns = COLUMNS
                return numeric.reset_index(drop=True)  # pyright: ignore[reportReturnType]
        raise ValidationError(
            f"ssa: {raw.name} holds no {len(COLUMNS)}-column period life table "
            f"with at least {EXPECTED_AGES} single-year-of-age rows"
        )

    def check_values(self, table: pa.Table) -> None:
        """Check the table is a life table and not merely seven numeric columns.

        SSA has no independent oracle the way HLD has NCHS -- SSA *is* the
        publisher -- so what is checked here is the internal structure a period
        life table must have: complete single years of age from 0, remaining
        life expectancy falling with age, women outliving men at every age, and
        life expectancy at birth inside the band the US series has occupied.
        A parse that picked up the wrong table or shifted a column fails these.

        Args:
            table: The candidate table.

        Raises:
            ValidationError: When the table is not a well-formed life table.
        """
        frame = table.to_pandas()
        ages = frame["age"].tolist()
        if ages != list(range(len(ages))):
            raise ValidationError(
                f"ssa: ages are not complete single years from 0 (got "
                f"{ages[:3]}...{ages[-3:]})"
            )
        for sex in ("male", "female"):
            column = frame[f"{sex}_life_expectancy"]
            if not column.is_monotonic_decreasing:
                raise ValidationError(
                    f"ssa: {sex} life expectancy does not fall with age, so this "
                    "is not a life table"
                )
            low, high = E0_BOUNDS
            if not low < column.iloc[0] < high:
                raise ValidationError(
                    f"ssa: {sex} life expectancy at birth is {column.iloc[0]}, "
                    f"outside the plausible {low}-{high} band"
                )
        if not (frame["female_life_expectancy"] >= frame["male_life_expectancy"]).all():
            raise ValidationError(
                "ssa: male life expectancy exceeds female at some age, which no "
                "published US period life table does; the sex columns are "
                "probably swapped"
            )
