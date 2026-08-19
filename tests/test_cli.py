"""End-to-end tests for the three command line entry points."""

import pandas as pd
import pytest

from lost_years import hld, ssa, who


@pytest.fixture
def input_csv(tmp_path):
    """Write a small input file.

    Args:
        tmp_path: pytest temporary directory.

    Returns:
        Path to the written CSV.
    """
    path = tmp_path / "input.csv"
    pd.DataFrame(
        {
            "country": ["USA", "JPN"],
            "year": [2019, 2019],
            "sex": ["M", "F"],
            "age": [0, 0],
        }
    ).to_csv(path, index=False)
    return path


def test_ssa_cli(input_csv, tmp_path):
    """The SSA command writes its columns to the output file."""
    out = tmp_path / "out.csv"
    assert ssa.main([str(input_csv), "-o", str(out)]) == 0
    result = pd.read_csv(out)
    assert result["ssa_life_expectancy"].iloc[0] == 74.74


def test_hld_cli(input_csv, tmp_path):
    """The HLD command reproduces the NCHS figure through the CLI."""
    out = tmp_path / "out.csv"
    assert hld.main([str(input_csv), "-o", str(out)]) == 0
    result = pd.read_csv(out)
    assert result["hld_life_expectancy"].tolist() == [76.31, 87.45]
    assert result["hld_n_candidates"].tolist() == [1, 1]


def test_hld_cli_subpopulations(input_csv, tmp_path):
    """`--subpopulations` emits more rows than the input has."""
    out = tmp_path / "out.csv"
    assert hld.main([str(input_csv), "-o", str(out), "--subpopulations"]) == 0
    result = pd.read_csv(out)
    assert len(result) > 2


def test_who_cli(input_csv, tmp_path):
    """The WHO command writes life expectancy at birth."""
    out = tmp_path / "out.csv"
    assert who.main([str(input_csv), "-o", str(out)]) == 0
    result = pd.read_csv(out)
    assert result["who_life_expectancy_at_birth"].iloc[0] == pytest.approx(
        76.53, abs=0.005
    )


def test_who_cli_has_no_age_option(input_csv, tmp_path):
    """The WHO table has no age dimension, so the CLI does not offer one."""
    with pytest.raises(SystemExit):
        who.main([str(input_csv), "-a", "age", "-o", str(tmp_path / "out.csv")])


@pytest.mark.parametrize("module", [ssa, hld, who])
def test_cli_reports_a_missing_column(module, tmp_path):
    """A missing input column is an error, not a silent pass-through."""
    path = tmp_path / "bad.csv"
    pd.DataFrame({"nothing": [1]}).to_csv(path, index=False)
    assert module.main([str(path), "-o", str(tmp_path / "out.csv")]) == -1


def test_who_unknown_country_returns_no_match():
    """A country the WHO table does not carry returns nothing, with a reason."""
    df = pd.DataFrame({"country": ["XXX"], "sex": ["M"], "year": [2019]})
    row = who.lost_years_who(df).iloc[0]
    assert pd.isna(row["who_life_expectancy_at_birth"])
    assert row["who_match_status"] == "no WHO row for country, sex and year"


def test_hld_missing_data_file(monkeypatch):
    """When the packaged HLD file is absent the input comes back untouched."""
    monkeypatch.setattr(hld, "HLD_DATA", "/nonexistent/hld.csv.gz")
    df = pd.DataFrame({"country": ["USA"], "year": [2019], "sex": ["M"], "age": [0]})
    assert hld.lost_years_hld(df).equals(df)
