"""Tests for the `lost_years` command and the SSA parse it drives.

The SSA parser is exercised against a real archived ssa.gov page — the
Actuarial Life Table for 2021, a different release from the one the wheel
ships — rather than a fixture written to match the parser. ssa.gov refuses
automated clients from many networks, which is why the copy is archived in the
repository instead of fetched.
"""

from pathlib import Path

import pytest

from lost_years.cli import main
from lost_years.sources import get_source
from lost_years.sources.base import SourceUnavailableError
from lost_years.update import status

from .conftest import RAW

REPO = Path(__file__).resolve().parent.parent
SSA_PAGE = REPO / "data" / "ssa" / "source" / "table4c6-2021.html"
SSA_CSV = REPO / "data" / "ssa" / "source" / "ssa-2022.csv"

# SSA's published Actuarial Life Table for 2021, read off the archived page.
SSA_2021_E0 = {"male_life_expectancy": 73.54, "female_life_expectancy": 79.30}


class TestSSAParse:
    """The SSA page parse, against a genuine archived page."""

    def test_reads_the_published_life_expectancy_at_birth(self, tmp_path):
        """The 2021 table's e(0) comes out at SSA's published 73.54 and 79.30."""
        import pyarrow.parquet as pq

        source = get_source("ssa")
        out = tmp_path / "ssa.parquet"
        notes = source.build(SSA_PAGE, out)
        source.validate(out)
        assert notes["table_year"] == 2021

        frame = pq.read_table(out).to_pandas()
        assert len(frame) == 120
        assert (frame["year"] == 2021).all()
        for column, expected in SSA_2021_E0.items():
            assert frame[column].iloc[0] == expected

    def test_release_is_read_from_the_page(self):
        """The page names its own table year; the archive is the 2021 one."""
        assert get_source("ssa").release_of(SSA_PAGE) == "2021"

    def test_archived_csv_rebuilds_the_shipped_table(self, tmp_path):
        """The 2022 table the wheel ships is reproducible from its archived raw."""
        import pyarrow.parquet as pq

        from lost_years.datasets import resolve, sha256

        source = get_source("ssa")
        out = tmp_path / "ssa.parquet"
        source.build(SSA_CSV, out)
        source.validate(out)
        assert sha256(out) == sha256(resolve("ssa", "ssa.parquet"))
        assert pq.read_table(out).to_pandas()["male_life_expectancy"].iloc[0] == 74.74


class TestCLI:
    """The `lost_years` command."""

    def test_sources_prints_the_registry(self, capsys):
        """Every source's home, download URL and terms are printed."""
        assert main(["sources"]) == 0
        printed = capsys.readouterr().out
        assert "https://www.lifetable.de/File/GetDocument/data/hld.zip" in printed
        assert "ships in the wheel" in printed
        assert "CC BY 4.0" in printed

    def test_status_offline_lists_every_source(self, capsys):
        """The offline report names each source and where its table came from."""
        assert main(["status", "--offline"]) == 0
        printed = capsys.readouterr().out
        assert "data directory:" in printed
        for name in ("hld", "ssa", "who"):
            assert name in printed
        assert "shipped:" in printed
        assert "downloaded:" in printed

    def test_update_installs_and_reports(self, scratch_cache, capsys):
        """A successful update names the file, the row count and the release."""
        assert (
            main(
                [
                    "update",
                    "--source",
                    "who",
                    "--from-file",
                    str(RAW["who"]),
                    "--output",
                    str(scratch_cache / "who"),
                ]
            )
            == 0
        )
        printed = capsys.readouterr().out
        assert "installed" in printed
        assert "12,936 rows" in printed
        assert "upstream release 2021" in printed

    def test_update_exits_nonzero_when_it_refuses(self, tmp_path, capsys):
        """A rejected candidate is an error status, not a stack trace."""
        broken = tmp_path / "empty.json"
        broken.write_text('{"value": []}', encoding="utf-8")
        assert (
            main(
                [
                    "update",
                    "--source",
                    "who",
                    "--from-file",
                    str(broken),
                    "--output",
                    str(tmp_path / "out"),
                ]
            )
            == 1
        )
        assert "NOT updated" in capsys.readouterr().out

    def test_unknown_source_is_rejected_by_the_parser(self):
        """`--source hmd` is refused rather than silently doing nothing."""
        with pytest.raises(SystemExit):
            main(["update", "--source", "hmd"])


class TestStalenessComparison:
    """Being ahead of what upstream announces is not being stale."""

    def test_release_ahead_of_upstream_is_current(self, seeded_cache, monkeypatch):
        """HLD's archive timestamp runs ahead of its own "What's New" page."""
        del seeded_cache
        monkeypatch.setattr(
            type(get_source("hld")), "upstream_release", lambda self: "2020-01-01"
        )
        report = status("hld")
        assert report.state == "current"
        assert "ahead of" in report.note

    def test_newer_release_upstream_is_stale(self, seeded_cache, monkeypatch):
        """A later release upstream is reported, with the command that gets it."""
        del seeded_cache
        monkeypatch.setattr(
            type(get_source("hld")), "upstream_release", lambda self: "2099-01-01"
        )
        report = status("hld")
        assert report.state == "stale"
        assert "lost_years update --source hld" in report.note

    def test_unreachable_upstream_is_unknown_not_current(
        self, seeded_cache, monkeypatch
    ):
        """A refused request must not be read as confirmation of currency."""
        del seeded_cache

        def refuse(self):
            raise SourceUnavailableError("ssa: returned HTTP 403")

        monkeypatch.setattr(type(get_source("hld")), "upstream_release", refuse)
        report = status("hld")
        assert report.state == "unknown"
        assert "403" in report.note
