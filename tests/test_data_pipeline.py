"""Tests for the update pipeline: schemas, manifests, and refusing bad data.

The point of the pipeline is that a bad upstream cannot become the user's data.
Most of what is asserted here is therefore a *refusal*: a truncated archive, a
scrambled table and an archive with the wrong shape each have to be rejected,
and the table that was already installed has to survive the attempt untouched.
"""

import gzip
import json
import shutil
import zipfile
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from lost_years import lost_years_hld
from lost_years.datasets import (
    ValidationError,
    data_dir,
    install,
    manifest_for,
    read_manifest,
    resolve,
    sha256,
    shipped_path,
)
from lost_years.sources import REGISTRY, get_source
from lost_years.sources.hld import NCHS_USA_MALE_E0
from lost_years.update import STATE_DAMAGED, STATE_MISSING, status, update

from .conftest import RAW, REPO, clear_table_caches

HLD_ZIP = RAW["hld"]
WHO_JSON = RAW["who"]


class TestShippedTable:
    """SSA is the one table inside the wheel, and it is typed Parquet."""

    def test_only_ssa_ships(self):
        """No other source has a file in the import package."""
        package_data = Path(str(resolve("ssa", "ssa.parquet"))).parent.parent
        tables = sorted(
            path.relative_to(package_data).as_posix()
            for path in package_data.rglob("*")
            if path.is_file() and path.suffix in {".parquet", ".csv", ".gz", ".zip"}
        )
        assert tables == ["ssa/ssa.parquet"]

    def test_shipped_ssa_carries_a_manifest(self):
        """The shipped table records where it came from and when."""
        manifest = read_manifest(resolve("ssa", "ssa.parquet"))
        assert manifest is not None
        assert manifest["source"] == "ssa"
        assert manifest["upstream_release"] == "2022"
        assert manifest["rows"] == 120
        assert manifest["source_url"].startswith("https://www.ssa.gov/")
        assert manifest["sha256"] == sha256(resolve("ssa", "ssa.parquet"))


class TestDeclaredSchemas:
    """Every derived table conforms to the Arrow schema its source declares."""

    @pytest.mark.parametrize("name", sorted(REGISTRY))
    def test_installed_table_matches_the_declared_schema(self, name):
        """The file on disk has exactly the declared fields, types and nullability."""
        source = get_source(name)
        found = pq.read_schema(resolve(name, source.filename)).remove_metadata()
        assert found == source.schema()

    def test_hld_logical_dtypes(self):
        """The HLD types are the sized, dictionary-encoded ones, not defaults."""
        schema = get_source("hld").schema()
        assert (
            str(schema.field("country").type)
            == "dictionary<values=string, indices=int16, ordered=0>"
        )
        assert str(schema.field("year1").type) == "int16"
        assert str(schema.field("type_lt").type) == "int8"
        assert str(schema.field("life_expectancy").type) == "double"
        assert not schema.field("life_expectancy").nullable
        assert schema.field("life_expectancy_published").nullable

    def test_ssa_logical_dtypes(self):
        """Age and year are 16-bit ints; the rates and expectancies are doubles."""
        schema = get_source("ssa").schema()
        assert str(schema.field("age").type) == "int16"
        assert str(schema.field("year").type) == "int16"
        assert str(schema.field("male_life_expectancy").type) == "double"
        assert all(not field.nullable for field in schema)


class TestManifest:
    """Every derived table says where it came from."""

    @pytest.mark.parametrize("name", ["hld", "who"])
    def test_manifest_records_provenance(self, name):
        """Source URL, upstream release, timestamp, row count and digest."""
        source = get_source(name)
        table = resolve(name, source.filename)
        manifest = read_manifest(table)
        assert manifest is not None
        assert manifest["source_url"] == source.download_url
        assert manifest["home_url"] == source.home_url
        assert manifest["licence"] == source.licence
        assert manifest["upstream_release"]
        assert manifest["fetched_at"].endswith("+00:00")
        assert manifest["rows"] == pq.read_metadata(table).num_rows
        assert manifest["sha256"] == sha256(table)
        assert manifest["raw_sha256"] == sha256(RAW[name])
        assert [field["name"] for field in manifest["schema"]] == source.schema().names

    def test_hld_manifest_counts_the_lines_it_could_not_read(self):
        """The 1,290 comma-decimal lines are counted, not silently skipped."""
        notes = read_manifest(resolve("hld", "hld.parquet"))["build_notes"]
        assert notes["malformed_lines_dropped"] == 1290
        assert notes["source_data_lines"] == 2183719
        assert notes["source_data_lines"] - notes["malformed_lines_dropped"] == 2182429

    def test_hld_release_comes_from_the_archive(self):
        """The release identifier is read out of the artifact, not off a page."""
        assert (
            read_manifest(resolve("hld", "hld.parquet"))["upstream_release"]
            == "2025-04-07"
        )


class TestRefusesBadData:
    """A candidate that fails a check is not installed."""

    def _corrupt_zip(self, tmp_path: Path, transform) -> Path:
        """Rewrite the pooled file inside a copy of hld.zip.

        Args:
            tmp_path: Where to write the copy.
            transform: Callable taking and returning the pooled file's bytes.

        Returns:
            Path to the rewritten archive.
        """
        with zipfile.ZipFile(HLD_ZIP) as archive:
            info = archive.getinfo("res")
            body = transform(archive.read("res"))
        target = tmp_path / "hld.zip"
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(info, body)
        return target

    def test_truncated_download_is_rejected(self, tmp_path, seeded_cache):
        """A short file fails the row-count contract and nothing is swapped in."""
        before = sha256(seeded_cache / "hld" / "hld.parquet")
        broken = self._corrupt_zip(
            tmp_path, lambda body: b"\n".join(body.split(b"\n")[:500_000])
        )
        with pytest.raises(ValidationError, match="truncated or partial"):
            update("hld", from_file=broken, destination=seeded_cache / "hld")
        assert sha256(seeded_cache / "hld" / "hld.parquet") == before

    def test_altered_life_expectancy_is_rejected(self, tmp_path, seeded_cache):
        """A file of the right size and shape still has to reproduce NCHS."""
        before = sha256(seeded_cache / "hld" / "hld.parquet")

        def bump_usa_2019(body: bytes) -> bytes:
            return body.replace(b",76.31,76.31", b",70.00,70.00")

        broken = self._corrupt_zip(tmp_path, bump_usa_2019)
        with pytest.raises(ValidationError, match="USA male life expectancy at birth"):
            update("hld", from_file=broken, destination=seeded_cache / "hld")
        assert sha256(seeded_cache / "hld" / "hld.parquet") == before

    def test_archive_without_the_pooled_file_is_rejected(self, tmp_path, seeded_cache):
        """An archive holding something else entirely never reaches the build."""
        before = sha256(seeded_cache / "hld" / "hld.parquet")
        target = tmp_path / "hld.zip"
        with zipfile.ZipFile(target, "w") as archive:
            archive.writestr("readme.txt", "not a life table")
        with pytest.raises(ValidationError, match="not the expected 'res'"):
            update("hld", from_file=target, destination=seeded_cache / "hld")
        assert sha256(seeded_cache / "hld" / "hld.parquet") == before

    def test_who_payload_with_scrambled_sexes_is_rejected(
        self, tmp_path, scratch_cache
    ):
        """Swapping male and female breaks the both-sexes ordering check."""
        records = json.loads(gzip.decompress(WHO_JSON.read_bytes()))
        swap = {"SEX_MLE": "SEX_FMLE", "SEX_FMLE": "SEX_MLE", "SEX_BTSX": "SEX_BTSX"}
        for record in records["value"]:
            if record["SpatialDim"] < "M":
                record["Dim1"] = swap[record["Dim1"]]
        broken = tmp_path / "WHOSIS_000001.json"
        broken.write_text(json.dumps(records), encoding="utf-8")
        with pytest.raises(ValidationError, match="sex labels"):
            update("who", from_file=broken, destination=scratch_cache / "who")
        assert not (scratch_cache / "who" / "who.parquet").exists()

    def test_a_rejected_update_leaves_no_debris(self, tmp_path, seeded_cache):
        """The staging file is gone whether the update succeeded or not."""
        target = tmp_path / "hld.zip"
        with zipfile.ZipFile(target, "w") as archive:
            archive.writestr("readme.txt", "not a life table")
        with pytest.raises(ValidationError):
            update("hld", from_file=target, destination=seeded_cache / "hld")
        leftovers = [
            path.name
            for path in (seeded_cache / "hld").iterdir()
            if path.name.startswith(".")
        ]
        assert leftovers == []


class TestUpdateInstalls:
    """A passing candidate lands, with its manifest, and is what gets read."""

    def test_update_from_an_empty_cache(self, scratch_cache):
        """From nothing to a working table and a manifest beside it."""
        assert status("hld", check_upstream=False).state == STATE_MISSING
        result = update("hld", from_file=HLD_ZIP, destination=scratch_cache / "hld")
        assert result.replaced is False
        assert result.path == scratch_cache / "hld" / "hld.parquet"
        assert manifest_for(result.path).exists()
        assert result.manifest["rows"] == 2_182_429

        clear_table_caches()
        row = lost_years_hld(
            _query("USA", 2019, "M", 0),
        ).iloc[0]
        assert row["hld_life_expectancy"] == NCHS_USA_MALE_E0[2019]

    def test_a_second_update_replaces_the_first(self, seeded_cache):
        """Re-running reports a replacement rather than a fresh install."""
        result = update("hld", from_file=HLD_ZIP, destination=seeded_cache / "hld")
        assert result.replaced is True

    def test_downloaded_table_wins_over_the_shipped_one(self, scratch_cache):
        """`lost_years update` is how a user replaces a stale packaged table."""
        assert resolve("ssa", "ssa.parquet") == shipped_path("ssa", "ssa.parquet")
        update(
            "ssa",
            from_file=REPO / "data" / "ssa" / "source" / "ssa-2022.csv",
            destination=scratch_cache / "ssa",
        )
        assert resolve("ssa", "ssa.parquet") == scratch_cache / "ssa" / "ssa.parquet"


class TestStatus:
    """The staleness report, without going near the network."""

    def test_missing_table_is_reported_as_missing(self, scratch_cache):
        """A source with nothing installed says so and names the fix."""
        del scratch_cache
        report = status("hld", check_upstream=False)
        assert report.state == STATE_MISSING
        assert "lost_years update --source hld" in report.note

    def test_installed_table_reports_its_release(self):
        """The report reads the release out of the manifest."""
        report = status("hld", check_upstream=False)
        assert report.kind == "downloaded"
        assert report.installed_release == "2025-04-07"
        assert report.rows == 2_182_429

    def test_a_table_that_no_longer_matches_its_manifest_is_flagged(self, seeded_cache):
        """An interrupted or edited install is reported, not read as if fine."""
        table = seeded_cache / "hld" / "hld.parquet"
        shutil.copy(resolve("ssa", "ssa.parquet"), table)
        assert status("hld", check_upstream=False).state == STATE_DAMAGED

    def test_shipped_ssa_is_reported_as_shipped(self, scratch_cache):
        """With an empty data directory, SSA still resolves to the wheel copy."""
        del scratch_cache
        assert status("ssa", check_upstream=False).kind == "shipped"


class TestAtomicInstall:
    """The swap itself."""

    def test_install_replaces_in_place(self, tmp_path):
        """The published name is only ever renamed onto, never written through."""
        destination = tmp_path / "dest"
        source_table = resolve("ssa", "ssa.parquet")
        manifest = read_manifest(source_table)
        first = install(source_table, manifest, destination)
        original = first.read_bytes()
        second = install(source_table, manifest, destination)
        assert first == second
        assert second.read_bytes() == original
        assert sorted(path.name for path in destination.iterdir()) == [
            "ssa.parquet",
            "ssa.parquet.manifest.json",
        ]


def _query(country, year, sex, age):
    """Build a one-row input frame.

    Args:
        country: ISO-3 country code.
        year: Calendar year.
        sex: Sex token.
        age: Exact age.

    Returns:
        A single-row DataFrame in the default column layout.
    """
    import pandas as pd

    return pd.DataFrame(
        {"country": [country], "year": [year], "sex": [sex], "age": [age]}
    )


def test_data_dir_honours_the_environment(scratch_cache):
    """The data directory is overridable, which is how the suite stays offline."""
    assert data_dir() == scratch_cache
