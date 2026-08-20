"""Fetch the pooled Human Life-Table Database file and derive the lookup table.

lifetable.de asks that users download their own copy rather than be handed one
("Please do not pass your copy of these data to other users. Rather refer them
to the HLD website, where they may download the data for themselves"), so this
package ships no HLD data at all. ``lost_years update --source hld`` is how a
user gets it, and it is a plain HTTP GET: the long-standing claim that HLD
needs a manual download came from issuing ``HEAD``, which the server answers
with 405 while answering ``GET`` with 200.
"""

import logging
import re
import zipfile
from datetime import date
from pathlib import Path
from typing import IO, Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from ..datasets import ValidationError
from ..hld import (
    DEFAULT_MAX_EX_DISCREPANCY,
    TABLE_KEY,
    eligible_tables,
    select_life_expectancy,
)
from .base import Source

logger = logging.getLogger(__name__)

# The member of hld.zip holding the pooled file: a bare CSV with no extension.
ZIP_MEMBER = "res"

# The 21-column upstream header. The other life-table functions -- m(x), q(x),
# l(x), d(x), L(x), T(x) -- play no part in a lookup and are not carried.
SOURCE_COLUMNS = [
    "Country",
    "Region",
    "Residence",
    "Ethnicity",
    "SocDem",
    "Version",
    "Ref-ID",
    "Year1",
    "Year2",
    "TypeLT",
    "Sex",
    "Age",
    "AgeInt",
    "e(x)",
    "e(x)Orig",
]

# Read as text: the sub-population codes and Ref-ID are alphanumeric codes that
# a float round-trip corrupts, and e(x)Orig uses "." for missing.
STRING_COLUMNS = [
    "Country",
    "Region",
    "Residence",
    "Ethnicity",
    "SocDem",
    "Ref-ID",
    "e(x)Orig",
]

RENAMED = {
    "Country": "country",
    "Region": "region",
    "Residence": "residence",
    "Ethnicity": "ethnicity",
    "SocDem": "socdem",
    "Version": "version",
    "Ref-ID": "ref_id",
    "Year1": "year1",
    "Year2": "year2",
    "TypeLT": "type_lt",
    "Age": "age",
    "AgeInt": "age_interval",
    "e(x)": "life_expectancy",
    "e(x)Orig": "life_expectancy_published",
}

CODE_COLUMNS = ["region", "residence", "ethnicity", "socdem"]

COLUMN_ORDER = [
    "country",
    "region",
    "residence",
    "ethnicity",
    "socdem",
    "version",
    "ref_id",
    "ref_id_sort",
    "year1",
    "year2",
    "type_lt",
    "sex",
    "age",
    "age_interval",
    "life_expectancy",
    "life_expectancy_published",
    "ex_discrepancy",
]

NATIONAL_CODE = "0"

# The oracle. NCHS publishes US male life expectancy at birth of 76.2 (2018),
# 76.3 (2019), 74.2 (2020) and 73.5 (2021); HLD carries the same tables to two
# decimals. Every step of the selection rule has to be right for these to come
# out, and the 2019-2020 fall is the COVID drop, so a rule that reaches for a
# five-year period table instead of the single-year one loses it entirely.
NCHS_USA_MALE_E0 = {2018: 76.22, 2019: 76.31, 2020: 74.19, 2021: 73.55}

# e(x)Orig is what makes the quarantine possible. A parse that lost it would
# leave every table looking self-consistent, so the share that carries one is
# checked rather than assumed.
MIN_PUBLISHED_SHARE = 0.90

WHATS_NEW_URL = "https://www.lifetable.de/Data/WhatsNew"
RELEASE_DATE = re.compile(r"\b(\d{2})\.(\d{2})\.(\d{4})\b")


def normalise_code(codes: pd.Series) -> pd.Series:
    """Repair sub-population codes that a float round-trip damaged.

    HLD writes a literal ``NA`` in ``Region`` for countries with no regional
    subdivisions, which pandas reads as missing. The codebook has no "region
    unknown" code and every such row is a whole-country table (NIU, KIR, NRU,
    and the single-year national tables for HUN 2018, IRN 2004, ISR 2013-17 and
    SWE 2019), so missing maps to ``'0'``.

    The trailing ``.0`` strip is defensive rather than needed: the raw upstream
    file has none, but a reader that omits ``dtype=`` turns ``0`` into ``0.0``,
    and that is exactly how 181,953 whole-country rows were lost once already.

    Args:
        codes: Raw code column, read as strings.

    Returns:
        Codes with any trailing ``.0`` removed and missing values set to "0".
    """
    out = codes.fillna(NATIONAL_CODE).astype(str).str.strip()
    return out.str.replace(r"^(\d+)\.0+$", r"\1", regex=True)


def count_source_lines(handle: IO[bytes]) -> tuple[int, int]:
    """Count data lines and malformed data lines in the pooled file.

    This exists to cross-check the reader rather than to trust it. The pooled
    file contains life tables written with a comma as the decimal separator in
    a comma-delimited file, so those rows carry more fields than the header
    declares and cannot be read; counting them here, without going through
    pandas, is an independent measure of how many rows the build drops.

    Args:
        handle: Binary stream positioned at the start of the file.

    Returns:
        Total data lines, and how many of them have the wrong field count.
    """
    header = handle.readline()
    expected = header.count(b",")
    total = 0
    malformed = 0
    for line in handle:
        if not line.strip():
            continue
        total += 1
        if line.count(b",") != expected:
            malformed += 1
    return total, malformed


class HLD(Source):
    """The pooled Human Life-Table Database file."""

    name = "hld"
    title = "Human Life-Table Database"
    home_url = "https://www.lifetable.de/"
    download_url = "https://www.lifetable.de/File/GetDocument/data/hld.zip"
    license = (
        "No affirmative redistribution grant. lifetable.de asks that users "
        "download their own copy; see https://www.lifetable.de/ for the user "
        "agreement."
    )
    filename = "hld.parquet"
    min_rows = 2_182_429

    def schema(self) -> pa.Schema:
        """Return the Arrow schema of the derived HLD table.

        Returns:
            The declared schema.
        """
        return pa.schema(
            [
                pa.field(
                    "country", pa.dictionary(pa.int16(), pa.string()), nullable=False
                ),
                pa.field(
                    "region", pa.dictionary(pa.int16(), pa.string()), nullable=False
                ),
                pa.field(
                    "residence", pa.dictionary(pa.int16(), pa.string()), nullable=False
                ),
                pa.field(
                    "ethnicity", pa.dictionary(pa.int16(), pa.string()), nullable=False
                ),
                pa.field(
                    "socdem", pa.dictionary(pa.int16(), pa.string()), nullable=False
                ),
                pa.field("version", pa.int8(), nullable=False),
                pa.field(
                    "ref_id", pa.dictionary(pa.int32(), pa.string()), nullable=False
                ),
                pa.field("ref_id_sort", pa.float64(), nullable=True),
                pa.field("year1", pa.int16(), nullable=False),
                pa.field("year2", pa.int16(), nullable=False),
                pa.field("type_lt", pa.int8(), nullable=False),
                pa.field("sex", pa.dictionary(pa.int8(), pa.string()), nullable=False),
                pa.field("age", pa.int16(), nullable=False),
                pa.field("age_interval", pa.int16(), nullable=False),
                pa.field("life_expectancy", pa.float64(), nullable=False),
                pa.field("life_expectancy_published", pa.float64(), nullable=True),
                pa.field("ex_discrepancy", pa.float64(), nullable=True),
            ]
        )

    def fetch(self, workdir: Path) -> Path:
        """Download hld.zip.

        Args:
            workdir: Scratch directory to download into.

        Returns:
            Path to the downloaded archive.
        """
        return self.download(self.download_url, workdir / "hld.zip")

    def release_of(self, raw: Path) -> str:
        """Read the release date out of the archive itself.

        The zip stores the modification time of its single member, and that
        time is the release: the 07.04.2025 release carries 2025-04-07. Taking
        the identifier from the artifact rather than from the page it was
        linked on means the manifest describes the file that was actually
        built, even when the two disagree.

        Args:
            raw: Downloaded hld.zip.

        Returns:
            The release date as ``YYYY-MM-DD``.

        Raises:
            ValidationError: When the archive does not hold the pooled file.
        """
        with zipfile.ZipFile(raw) as archive:
            names = archive.namelist()
            if ZIP_MEMBER not in names:
                raise ValidationError(
                    f"hld: archive holds {names}, not the expected {ZIP_MEMBER!r}"
                )
            stamp = archive.getinfo(ZIP_MEMBER).date_time
        return date(stamp[0], stamp[1], stamp[2]).isoformat()

    def upstream_release(self) -> str:
        """Read the newest release date off the HLD "What's New" page.

        Returns:
            The most recent release date as ``YYYY-MM-DD``.

        Raises:
            ValidationError: When the page carries no recognisable date.
        """
        page = self.get_text(WHATS_NEW_URL)
        dates = [
            date(int(year), int(month), int(day))
            for day, month, year in RELEASE_DATE.findall(page)
        ]
        if not dates:
            raise ValidationError(f"hld: no release date found at {WHATS_NEW_URL}")
        return max(dates).isoformat()

    def build(self, raw: Path, destination: Path) -> dict[str, Any]:
        """Derive the typed lookup table from hld.zip.

        Args:
            raw: Downloaded hld.zip.
            destination: Path to write the Parquet file to.

        Returns:
            Build notes for the manifest.

        Raises:
            ValidationError: When the reader and the independent line count
                disagree about how many rows the file holds.
        """
        with zipfile.ZipFile(raw) as archive, archive.open(ZIP_MEMBER) as stream:
            total_lines, malformed_lines = count_source_lines(stream)
        with zipfile.ZipFile(raw) as archive, archive.open(ZIP_MEMBER) as stream:
            # Every column is read, not just the fifteen that are kept: the
            # field count is what identifies a malformed line, and restricting
            # `usecols` makes pandas keep such a line with its values shifted
            # one column left -- which is how e(x) of 99775 gets into a table.
            frame = pd.read_csv(
                stream,
                dtype=dict.fromkeys(STRING_COLUMNS, str),
                on_bad_lines="skip",
                low_memory=False,
            )
        if len(frame) + malformed_lines != total_lines:
            raise ValidationError(
                f"hld: read {len(frame)} rows and counted {malformed_lines} "
                f"malformed lines, which does not account for {total_lines} "
                "data lines in the pooled file"
            )
        logger.info(
            "Read %d HLD rows; dropped %d malformed lines", len(frame), malformed_lines
        )

        table = self._normalise(frame)
        arrow = pa.Table.from_pandas(table, schema=self.schema(), preserve_index=False)
        pq.write_table(
            arrow,
            destination,
            compression="zstd",
            use_dictionary=True,
            write_statistics=True,
        )
        return {
            "source_data_lines": total_lines,
            "malformed_lines_dropped": malformed_lines,
            "rows_dropped_for_missing_key": int(len(frame) - len(table)),
            "malformed_line_note": (
                "Life tables written with a comma decimal separator inside a "
                "comma-delimited file. All belong to sub-national or "
                "sub-population tables, so no whole-country answer changes."
            ),
        }

    @staticmethod
    def _normalise(frame: pd.DataFrame) -> pd.DataFrame:
        """Turn the raw pooled columns into the derived table.

        Args:
            frame: Raw pooled file as read.

        Returns:
            The derived table, in schema order.
        """
        table = frame[SOURCE_COLUMNS].rename(columns=RENAMED)  # pyright: ignore[reportCallIssue]
        table["sex"] = frame["Sex"].map({1: "M", 2: "F"})  # pyright: ignore[reportArgumentType]
        for column in CODE_COLUMNS:
            table[column] = normalise_code(table[column])  # pyright: ignore[reportArgumentType]
        for column in ("life_expectancy", "life_expectancy_published"):
            table[column] = pd.to_numeric(table[column], errors="coerce")

        gap = (table["life_expectancy"] - table["life_expectancy_published"]).abs()
        table["ex_discrepancy"] = gap.groupby(
            [table[key] for key in TABLE_KEY], dropna=False
        ).transform("max")
        # Ref-ID sorts as NNNN.PP, so lexical order would put "9.01" above
        # "1042.01"; the tie-break needs the numeric order.
        table["ref_id_sort"] = pd.to_numeric(table["ref_id"], errors="coerce")
        table = table.dropna(
            subset=["country", "sex", "life_expectancy", "year1", "year2"]
        )
        return table[COLUMN_ORDER].reset_index(drop=True)  # pyright: ignore[reportReturnType]

    def check_values(self, table: pa.Table) -> None:
        """Reproduce the published US life tables through the selection rule.

        Args:
            table: The candidate table.

        Raises:
            ValidationError: When the rule does not reproduce NCHS, when the
                national table is not one row per life table and age, or when
                the published-e(x) column that the quarantine depends on is
                mostly missing.
        """
        frame = table.to_pandas()
        published = frame["life_expectancy_published"].notna().mean()
        if published < MIN_PUBLISHED_SHARE:
            raise ValidationError(
                f"hld: only {published:.1%} of rows carry a published e(x), "
                f"below the {MIN_PUBLISHED_SHARE:.0%} needed for the quarantine "
                "cross-check to mean anything"
            )

        national = eligible_tables(
            frame, national_only=True, max_ex_discrepancy=DEFAULT_MAX_EX_DISCREPANCY
        )
        duplicated = national.duplicated([*TABLE_KEY, "age"]).sum()
        if duplicated:
            raise ValidationError(
                f"hld: {duplicated} national rows share a life table and an age, "
                "so a lookup would have to choose arbitrarily between values"
            )

        for year, expected in NCHS_USA_MALE_E0.items():
            record = select_life_expectancy(national, "USA", year, "M", 0)
            found = record["hld_life_expectancy"]
            if found != expected:
                raise ValidationError(
                    f"hld: USA male life expectancy at birth in {year} came out "
                    f"as {found}, not the published {expected}"
                )
