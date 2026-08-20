"""Fetch WHO life expectancy at birth from the Global Health Observatory.

GHO datasets are CC BY 4.0, so redistribution would be allowed; the table is
fetched rather than shipped because a packaged copy is stale the day WHO
publishes a revision and nothing in the wheel would say so. The OData endpoint
is public and needs no credentials.

The indicator is ``WHOSIS_000001``, life expectancy *at birth*: one value per
population, year and sex, with no age dimension. That is a property of the
indicator, not of this package, and it is why :func:`lost_years.lost_years_who`
refuses an age column.
"""

import gzip
import json
import logging
from importlib.resources import files
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from ..datasets import ValidationError
from .base import Source

logger = logging.getLogger(__name__)

INDICATOR = "WHOSIS_000001"
API_URL = f"https://ghoapi.azureedge.net/api/{INDICATOR}"
LATEST_YEAR_URL = f"{API_URL}?%24select=TimeDim&%24orderby=TimeDim%20desc&%24top=1"
HOME_URL = "https://www.who.int/data/gho"

# ISO-3166 alpha-3 to country name, built from the REST Countries API. GHO
# returns only the code, and its `ParentLocation` is the WHO *region*, which is
# how Somalia came to be labeled "Eastern Mediterranean" in an earlier release.
COUNTRY_NAMES = files("lost_years") / "data" / "who" / "iso_country_mapping.json"

COLUMNS = [
    "country_code",
    "country_name",
    "spatial_type",
    "year",
    "sex_code",
    "life_expectancy",
    "low_ci",
    "high_ci",
]

# Life expectancy at birth has never been published outside this band for any
# population in the series; a shifted column or a wrong indicator would be.
LIFE_EXPECTANCY_BOUNDS = (15.0, 100.0)

MIN_COUNTRIES = 180

SEX_CODES = {"SEX_MLE": "MLE", "SEX_FMLE": "FMLE", "SEX_BTSX": "BTSX"}

# Both-sexes life expectancy is a weighted average of the two single-sex
# figures, so it must lie between them. WHO rounds and revises independently,
# so a small share of country-years sit marginally outside; a parse that
# scrambled the sex labels would put a large share outside.
MAX_UNORDERED_SHARE = 0.01

# Women outlive men in almost every population WHO covers: 98.5% of the 4,312
# country-years in the shipped release, the exceptions being the Gulf states
# and a handful of central African country-years. The check is deliberately
# asymmetric, because the both-sexes test above is not: exchanging the male and
# female labels leaves BTSX sitting between them just as before, and only this
# notices.
MIN_FEMALE_ADVANTAGE_SHARE = 0.95


def read_payload(raw: Path) -> list[dict[str, Any]]:
    """Read an OData payload, gzipped or not.

    The archived copy in ``data/who/source/`` is gzipped because 7.7 MB of
    JSON compresses to 0.6 MB; a freshly downloaded one is not.

    Args:
        raw: Downloaded or archived payload.

    Returns:
        The records the payload carries.

    Raises:
        ValidationError: When the payload holds no rows.
    """
    if raw.suffix == ".gz":
        text = gzip.decompress(raw.read_bytes()).decode("utf-8")
    else:
        text = raw.read_text(encoding="utf-8")
    records = json.loads(text).get("value") or []
    if not records:
        raise ValidationError(f"who: {raw.name} holds no rows")
    return records


class WHO(Source):
    """WHO Global Health Observatory life expectancy at birth."""

    name = "who"
    title = "WHO Global Health Observatory, life expectancy at birth"
    home_url = HOME_URL
    download_url = API_URL
    license = "CC BY 4.0"
    filename = "who.parquet"
    min_rows = 12_936

    def schema(self) -> pa.Schema:
        """Return the Arrow schema of the derived WHO table.

        Returns:
            The declared schema.
        """
        return pa.schema(
            [
                pa.field(
                    "country_code",
                    pa.dictionary(pa.int16(), pa.string()),
                    nullable=False,
                ),
                pa.field(
                    "country_name",
                    pa.dictionary(pa.int16(), pa.string()),
                    nullable=False,
                ),
                pa.field(
                    "spatial_type",
                    pa.dictionary(pa.int8(), pa.string()),
                    nullable=False,
                ),
                pa.field("year", pa.int16(), nullable=False),
                pa.field(
                    "sex_code", pa.dictionary(pa.int8(), pa.string()), nullable=False
                ),
                pa.field("life_expectancy", pa.float64(), nullable=False),
                pa.field("low_ci", pa.float64(), nullable=True),
                pa.field("high_ci", pa.float64(), nullable=True),
            ]
        )

    def fetch(self, workdir: Path) -> Path:
        """Download the whole indicator as OData JSON.

        Args:
            workdir: Scratch directory to download into.

        Returns:
            Path to the downloaded JSON.
        """
        return self.download(API_URL, workdir / f"{INDICATOR}.json")

    def upstream_release(self) -> str:
        """Report the most recent year GHO publishes for this indicator.

        Returns:
            The year as a string.

        Raises:
            ValidationError: When the endpoint returns no year.
        """
        payload = json.loads(self.get_text(LATEST_YEAR_URL))
        values = payload.get("value") or []
        if not values:
            raise ValidationError(f"who: {LATEST_YEAR_URL} returned no rows")
        return str(values[0]["TimeDim"])

    def release_of(self, raw: Path) -> str:
        """Read the most recent year out of a payload.

        Args:
            raw: Downloaded or archived OData JSON.

        Returns:
            The year as a string.
        """
        return str(max(int(record["TimeDim"]) for record in read_payload(raw)))

    def build(self, raw: Path, destination: Path) -> dict[str, Any]:
        """Derive the typed WHO table from the OData payload.

        Args:
            raw: Downloaded or archived OData JSON.
            destination: Path to write the Parquet file to.

        Returns:
            Build notes for the manifest.

        Raises:
            ValidationError: When the payload carries an unrecognised sex code.
        """
        payload = pd.DataFrame(read_payload(raw))
        names = json.loads(Path(str(COUNTRY_NAMES)).read_text(encoding="utf-8"))

        unknown = set(payload["Dim1"].unique()) - set(SEX_CODES)
        if unknown:
            raise ValidationError(f"who: unrecognised sex codes {sorted(unknown)}")

        table = pd.DataFrame(
            {
                "country_code": payload["SpatialDim"].astype(str),
                "spatial_type": payload["SpatialDimType"].astype(str),
                "year": payload["TimeDim"].astype("int16"),
                "sex_code": payload["Dim1"].map(SEX_CODES),  # pyright: ignore[reportArgumentType]
                "life_expectancy": pd.to_numeric(
                    payload["NumericValue"], errors="coerce"
                ),
                "low_ci": pd.to_numeric(payload["Low"], errors="coerce"),
                "high_ci": pd.to_numeric(payload["High"], errors="coerce"),
            }
        )
        table["country_name"] = (
            table["country_code"].map(names).fillna(table["country_code"])
        )
        unnamed = int((table["country_name"] == table["country_code"]).sum())
        table = table.dropna(subset=["life_expectancy"])
        table = table[COLUMNS].sort_values(  # pyright: ignore[reportCallIssue]
            ["country_code", "year", "sex_code"], ignore_index=True
        )

        arrow = pa.Table.from_pandas(table, schema=self.schema(), preserve_index=False)
        pq.write_table(
            arrow,
            destination,
            compression="zstd",
            use_dictionary=True,
            write_statistics=True,
        )
        return {
            "indicator": INDICATOR,
            "rows_without_a_country_name": unnamed,
            "spatial_types": sorted(table["spatial_type"].unique().tolist()),
        }

    def check_values(self, table: pa.Table) -> None:
        """Check coverage, plausible values, and the sexes being in order.

        Args:
            table: The candidate table.

        Raises:
            ValidationError: When coverage is short, a value is implausible, the
                both-sexes figure does not sit between the single-sex ones, or
                the sexes have been exchanged.
        """
        frame = table.to_pandas()
        countries = frame.loc[
            frame["spatial_type"] == "COUNTRY", "country_code"
        ].nunique()
        if countries < MIN_COUNTRIES:
            raise ValidationError(
                f"who: {countries} countries, fewer than the {MIN_COUNTRIES} this "
                "indicator has always covered"
            )
        low, high = LIFE_EXPECTANCY_BOUNDS
        outside = frame[
            (frame["life_expectancy"] <= low) | (frame["life_expectancy"] >= high)
        ]
        if not outside.empty:
            raise ValidationError(
                f"who: {len(outside)} life expectancies outside {low}-{high} years, "
                f"e.g. {outside.iloc[0].to_dict()}"
            )
        wide = frame.pivot_table(
            index=["country_code", "year"], columns="sex_code", values="life_expectancy"
        ).dropna()
        low = wide[["MLE", "FMLE"]].min(axis=1)
        high = wide[["MLE", "FMLE"]].max(axis=1)
        unordered = (~wide["BTSX"].between(low, high)).mean()
        if unordered > MAX_UNORDERED_SHARE:
            raise ValidationError(
                f"who: both-sexes life expectancy lies outside the male-female "
                f"range for {unordered:.1%} of country-years, so the value column "
                "does not line up with the rows"
            )
        female_ahead = (wide["FMLE"] > wide["MLE"]).mean()
        if female_ahead < MIN_FEMALE_ADVANTAGE_SHARE:
            raise ValidationError(
                f"who: women outlive men in only {female_ahead:.1%} of "
                f"country-years, below the {MIN_FEMALE_ADVANTAGE_SHARE:.0%} this "
                "indicator has always shown; the sex labels are probably swapped"
            )
