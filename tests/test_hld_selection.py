"""Value-level regression tests for the HLD selection rule.

The oracle is the US National Center for Health Statistics. NCHS publishes male
life expectancy at birth of 76.2 (2018), 76.3 (2019), 74.2 (2020) and 73.5
(2021); HLD carries the same tables to two decimals. A wrong table choice moves
these numbers by whole years, and the 2019-2020 fall is the COVID drop, so a
rule that picks a five-year period table instead of the single-year one loses
it entirely.
"""

import pandas as pd
import pytest

from lost_years import lost_years_hld
from lost_years.hld import (
    OPEN_AGE_INTERVAL,
    load_hld_table,
    select_life_expectancy,
)
from lost_years.sources.hld import normalise_code

# NCHS published values, to the one decimal NCHS reports.
NCHS_USA_MALE_E0 = {2018: 76.2, 2019: 76.3, 2020: 74.2, 2021: 73.5}
# The same tables as HLD stores them.
HLD_USA_MALE_E0 = {2018: 76.22, 2019: 76.31, 2020: 74.19, 2021: 73.55}


@pytest.fixture(scope="module")
def national_table():
    """Load the eligible national life tables once for the module.

    Returns:
        The default (national, quarantined) HLD table.
    """
    return load_hld_table()


def query(country, year, sex, age):
    """Build a one-row input frame.

    Args:
        country: ISO-3 country code.
        year: Calendar year.
        sex: Sex token.
        age: Exact age.

    Returns:
        A single-row DataFrame in the default column layout.
    """
    return pd.DataFrame(
        {"country": [country], "year": [year], "sex": [sex], "age": [age]}
    )


class TestNCHSOracle:
    """The published US life tables, reproduced through the public entry point."""

    @pytest.mark.parametrize("year", sorted(HLD_USA_MALE_E0))
    def test_usa_male_life_expectancy_at_birth(self, year):
        """USA male e(0) matches NCHS for 2018-2021."""
        row = lost_years_hld(query("USA", year, "M", 0)).iloc[0]
        assert row["hld_match_status"] == "ok"
        assert row["hld_life_expectancy"] == HLD_USA_MALE_E0[year]
        assert abs(row["hld_life_expectancy"] - NCHS_USA_MALE_E0[year]) <= 0.05
        assert row["hld_year1"] == year
        assert row["hld_year2"] == year
        assert row["hld_n_candidates"] == 1

    def test_covid_drop_survives_table_selection(self):
        """The 2019-2020 fall in US male e(0) is 2.12 years."""
        before = lost_years_hld(query("USA", 2019, "M", 0)).iloc[0]
        after = lost_years_hld(query("USA", 2020, "M", 0)).iloc[0]
        drop = before["hld_life_expectancy"] - after["hld_life_expectancy"]
        assert drop == pytest.approx(2.12, abs=0.005)

    def test_usa_female_2019(self):
        """USA female e(0) in 2019 is 81.38 against a published 81.4."""
        row = lost_years_hld(query("USA", 2019, "F", 0)).iloc[0]
        assert row["hld_life_expectancy"] == 81.38
        assert round(row["hld_life_expectancy"], 1) == 81.4

    def test_japan_female_2019(self):
        """JPN female e(0) in 2019 is 87.45."""
        row = lost_years_hld(query("JPN", 2019, "F", 0)).iloc[0]
        assert row["hld_life_expectancy"] == 87.45


class TestCountryMatching:
    """Country codes are matched exactly, not as regular expressions."""

    def test_us_does_not_return_australia(self):
        """`US` is not a country code and must not match AUS."""
        row = lost_years_hld(query("US", 2019, "M", 0)).iloc[0]
        assert pd.isna(row["hld_life_expectancy"])
        assert row["hld_match_status"] == "no eligible life table for country"

    def test_aus_still_returns_australia(self):
        """The exact code still resolves."""
        row = lost_years_hld(query("AUS", 2019, "M", 0)).iloc[0]
        assert row["hld_country"] == "AUS"
        assert row["hld_match_status"] == "ok"

    def test_matching_is_case_insensitive(self):
        """Lower case input resolves to the same row as upper case."""
        lower = lost_years_hld(query("usa", 2019, "M", 0)).iloc[0]
        upper = lost_years_hld(query("USA", 2019, "M", 0)).iloc[0]
        assert lower["hld_life_expectancy"] == upper["hld_life_expectancy"]

    def test_regex_metacharacters_do_not_match(self):
        """A regular expression is treated as a literal code, so it matches nothing."""
        row = lost_years_hld(query("U.A", 2019, "M", 0)).iloc[0]
        assert row["hld_match_status"] == "no eligible life table for country"


class TestMissingInputs:
    """Missing values are refused rather than silently resolved."""

    def test_missing_age_does_not_become_age_zero(self):
        """A missing age used to fall through to age 0 and its e(0)."""
        row = lost_years_hld(query("USA", 2019, "M", float("nan"))).iloc[0]
        assert pd.isna(row["hld_life_expectancy"])
        assert row["hld_match_status"] == "missing age"

    def test_missing_year_is_refused(self):
        """A missing year has no closest match either."""
        row = lost_years_hld(query("USA", float("nan"), "M", 0)).iloc[0]
        assert row["hld_match_status"] == "missing year"

    def test_unrecognised_sex_is_refused(self):
        """An unmapped sex token no longer defaults to female."""
        row = lost_years_hld(query("USA", 2019, "unknown", 0)).iloc[0]
        assert row["hld_match_status"] == "unrecognised sex"

    def test_year_outside_coverage_is_refused(self):
        """HLD matches by containment, so a year no table covers returns nothing."""
        row = lost_years_hld(query("USA", 2500, "M", 0)).iloc[0]
        assert pd.isna(row["hld_life_expectancy"])
        assert row["hld_match_status"] == "no eligible life table covering year"


class TestUnitOfObservation:
    """One input row in, one output row out, chosen by a total order."""

    def test_output_has_one_row_per_input_row(self):
        """The default lookup never multiplies rows."""
        df = pd.read_csv("tests/input.csv")
        result = lost_years_hld(df)
        assert len(result) == len(df)
        assert list(result["country"]) == list(df["country"])

    def test_selection_is_deterministic(self):
        """Re-running the same query returns the same row."""
        first = lost_years_hld(query("SWE", 1900, "F", 40)).iloc[0]
        second = lost_years_hld(query("SWE", 1900, "F", 40)).iloc[0]
        assert first["hld_ref_id"] == second["hld_ref_id"]
        assert first["hld_life_expectancy"] == second["hld_life_expectancy"]

    def test_candidate_count_is_reported(self, national_table):
        """Residual ambiguity is exposed, not hidden."""
        record = select_life_expectancy(national_table, "USA", 2019, "M", 0)
        assert record["hld_n_candidates"] == 1
        # 1946 USA is covered by more than one equally narrow national table.
        crowded = select_life_expectancy(national_table, "NLD", 1946, "M", 0)
        assert crowded["hld_n_candidates"] > 1

    def test_national_table_is_unique_on_the_selection_key(self, national_table):
        """No two eligible rows share a full table key and age.

        This is the contract whose absence let the old code take ``iloc[0]``:
        once a life table and an age are fixed there is exactly one value, so
        every remaining choice is between *tables*, which the documented
        tie-break resolves.
        """
        key = [
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
            "age",
        ]
        assert not national_table.duplicated(key).any()


class TestFiltering:
    """The three filters that run before any query."""

    def test_normalise_code_repairs_float_round_trip(self):
        """`0.0` and a missing code both mean the whole country."""
        codes = pd.Series(["0", "0.0", "10.0", "S010", None])
        assert list(normalise_code(codes)) == ["0", "0", "10", "S010", "0"]

    def test_normalisation_recovers_the_lost_national_rows(self, national_table):
        """A naive `== '0'` filter keeps 550,429 rows; normalising keeps 717,457."""
        assert len(national_table) > 550_429

    def test_national_table_holds_only_whole_country_totals(self, national_table):
        """Every sub-population code is the total-population code."""
        for col in ("region", "residence", "ethnicity", "socdem"):
            assert set(national_table[col].unique()) == {"0"}

    def test_redundant_abridged_tables_are_dropped(self, national_table):
        """TypeLT 2 is HLD's own abridgement of TypeLT 1 from the same source."""
        assert 2 not in set(national_table["type_lt"].unique())

    def test_corrupt_table_is_quarantined(self):
        """ARG 1980 Ref-ID 1042.01 recalculates e(0)=79.11 against its own 65.48."""
        served = load_hld_table(national_only=True, max_ex_discrepancy=None)
        corrupt = served[
            (served["country"] == "ARG")
            & (served["ref_id"] == "1042.01")
            & (served["sex"] == "M")
            & (served["age"] == 0)
        ]
        assert corrupt.iloc[0]["life_expectancy"] == 79.11
        assert corrupt.iloc[0]["life_expectancy_published"] == 65.48

        eligible = load_hld_table()
        assert eligible[
            (eligible["country"] == "ARG") & (eligible["ref_id"] == "1042.01")
        ].empty

    def test_quarantine_changes_a_real_answer(self):
        """France 2010: the quarantine is what makes the answer right.

        Three national tables cover 2010. The 2010-2012 one (Ref-ID 3201.03)
        recalculates female life expectancy at birth to 81.51 against its own
        published 84.84, and the old rule picked it because its ``Year1``
        equalled the requested year. Quarantining it leaves Ref-ID 1765.01 and
        84.70, against INSEE's published 84.7 for 2010.
        """
        row = lost_years_hld(query("FRA", 2010, "F", 0)).iloc[0]
        assert row["hld_life_expectancy"] == 84.70
        assert row["hld_ref_id"] == "1765.01"
        assert row["hld_ex_discrepancy"] <= 2

        served = lost_years_hld(query("FRA", 2010, "F", 0), max_ex_discrepancy=None)
        assert served.iloc[0]["hld_life_expectancy"] == 81.51
        assert served.iloc[0]["hld_ex_discrepancy"] > 2

    def test_period_containment_changes_a_real_answer(self):
        """India 1950 comes from the 1941-1951 table, not the 1951-1961 one.

        Matching on the closest ``Year1`` answered 1950 from a period that
        starts in 1951, 6.17 years higher.
        """
        row = lost_years_hld(query("IND", 1950, "M", 0)).iloc[0]
        assert row["hld_year1"] == 1941
        assert row["hld_year2"] == 1951
        assert row["hld_life_expectancy"] == 35.93

    def test_countries_without_a_national_table_return_no_estimate(self):
        """Nine countries have only sub-national or sub-population tables."""
        no_national = ["BFA", "ETH", "GHA", "GMB", "GNB", "MOZ", "PSE", "TZA", "ZMB"]
        df = pd.DataFrame(
            {
                "country": no_national,
                "year": [2000] * len(no_national),
                "sex": ["M"] * len(no_national),
                "age": [0] * len(no_national),
            }
        )
        result = lost_years_hld(df)
        assert result["hld_life_expectancy"].isna().all()
        assert set(result["hld_match_status"]) == {"no eligible life table for country"}


class TestPeriodAndAgeIntervals:
    """Years are matched by containment; ages by the interval they fall in."""

    def test_multi_year_period_table_is_reachable(self):
        """A year covered only by a period table still resolves."""
        row = lost_years_hld(query("IND", 1955, "M", 0)).iloc[0]
        assert row["hld_match_status"] == "ok"
        assert row["hld_year1"] < 1955 < row["hld_year2"]

    def test_narrowest_period_wins(self):
        """A single-year table beats a period table covering the same year."""
        row = lost_years_hld(query("USA", 2019, "M", 0)).iloc[0]
        assert row["hld_year1"] == row["hld_year2"] == 2019

    def test_year_outside_every_period_needs_an_explicit_tolerance(self):
        """Lebanon's only national table is 1998, so 1997 is a reach."""
        strict = lost_years_hld(query("LBN", 1997, "F", 49)).iloc[0]
        assert strict["hld_match_status"] == "no eligible life table covering year"

        reached = lost_years_hld(query("LBN", 1997, "F", 49), year_tolerance=5).iloc[0]
        assert reached["hld_year1"] == 1998
        assert reached["hld_life_expectancy"] == 31.99
        assert reached["hld_match_status"] == "ok: nearest period, 1 year(s) away"

    def test_abridged_age_interval_is_exposed(self):
        """Ages 20, 22 and 24 all fall in the same [20, 25) band."""
        df = pd.DataFrame(
            {
                "country": ["IND"] * 3,
                "year": [1960] * 3,
                "sex": ["M"] * 3,
                "age": [20, 22, 24],
            }
        )
        result = lost_years_hld(df)
        assert list(result["hld_age"]) == [20, 20, 20]
        assert list(result["hld_age_interval"]) == [5, 5, 5]
        assert result["hld_life_expectancy"].nunique() == 1

    def test_open_top_interval_covers_every_older_age(self, national_table):
        """AgeInt 99 marks an interval with no upper bound."""
        record = select_life_expectancy(national_table, "USA", 2019, "M", 100)
        assert record["hld_age_interval"] == OPEN_AGE_INTERVAL
        older = select_life_expectancy(national_table, "USA", 2019, "M", 130)
        assert older["hld_age"] == record["hld_age"] == 100
        assert older["hld_life_expectancy"] == record["hld_life_expectancy"]

    def test_age_outside_every_interval_is_refused(self, national_table):
        """No interval starts below zero, so a negative age matches nothing."""
        record = select_life_expectancy(national_table, "USA", 2019, "M", -5)
        assert record["hld_match_status"] == "no age interval covering age"


class TestSubpopulations:
    """Sub-populations are opt-in and each resolved row is itself unambiguous."""

    def test_default_is_the_national_total(self):
        """One row, with every sub-population code at the total-population value."""
        result = lost_years_hld(query("USA", 2019, "M", 0))
        assert len(result) == 1
        assert result.iloc[0]["hld_region"] == "0"
        assert result.iloc[0]["hld_ethnicity"] == "0"

    def test_opt_in_returns_every_subpopulation(self):
        """The states and ethnic groups the default hides come back on request."""
        result = lost_years_hld(query("USA", 2019, "M", 0), subpopulations=True)
        assert len(result) > 1
        national = result[result["hld_region"] == "0"]
        assert 76.31 in set(national["hld_life_expectancy"])
        # The spread the old `iloc[0]` was choosing among, arbitrarily.
        assert result["hld_life_expectancy"].max() > 83
        assert result["hld_life_expectancy"].min() < 69
        assert (result["hld_n_candidates"] == 1).all()
