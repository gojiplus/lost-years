"""Tests for lost_years package."""

import logging

import pandas as pd
import pytest

from lost_years import lost_years_hld, lost_years_ssa, lost_years_who

# SSA period life table, 2022, remaining years at exact age.
SSA_2022 = {("M", 0): 74.74, ("F", 0): 80.18, ("M", 30): 46.51, ("F", 65): 20.12}

# WHO indicator WHOSIS_000001, life expectancy at birth.
WHO_AT_BIRTH = {("USA", 2019, "M"): 76.53, ("USA", 2019, "F"): 80.98}


class TestLostYears:
    """Test class for lost_years functions."""

    @pytest.fixture
    def sample_data(self):
        """Load sample data for testing.

        Returns:
            The packaged ten-row example input.
        """
        return pd.read_csv("tests/input.csv")

    @pytest.mark.parametrize(("sex", "age"), sorted(SSA_2022))
    def test_lost_years_ssa_values(self, sex, age):
        """SSA returns the published 2022 period life table figures."""
        df = pd.DataFrame({"age": [age], "sex": [sex], "year": [2022]})
        row = lost_years_ssa(df).iloc[0]
        assert row["ssa_match_status"] == "ok"
        assert row["ssa_year"] == 2022
        assert row["ssa_age"] == age
        assert row["ssa_life_expectancy"] == SSA_2022[(sex, age)]

    def test_lost_years_ssa_shape(self, sample_data):
        """One output row per input row, with the match status attached."""
        result = lost_years_ssa(sample_data)
        assert "ssa_life_expectancy" in result.columns
        assert len(result) == len(sample_data)
        assert "ssa_match_status" in result.columns

    def test_lost_years_hld(self, sample_data):
        """HLD appends its columns without changing the number of rows."""
        result = lost_years_hld(sample_data)
        assert "hld_life_expectancy" in result.columns
        assert "hld_year1" in result.columns
        assert "hld_age_interval" in result.columns
        assert len(result) == len(sample_data)

    @pytest.mark.parametrize(("country", "year", "sex"), sorted(WHO_AT_BIRTH))
    def test_lost_years_who_values(self, country, year, sex):
        """WHO returns life expectancy at birth for the requested year."""
        df = pd.DataFrame({"country": [country], "sex": [sex], "year": [year]})
        row = lost_years_who(df).iloc[0]
        assert row["who_match_status"] == "ok"
        assert row["who_year"] == year
        assert row["who_life_expectancy_at_birth"] == pytest.approx(
            WHO_AT_BIRTH[(country, year, sex)], abs=0.005
        )

    def test_lost_years_who_names_its_column_for_what_it_holds(self, sample_data):
        """The WHO table has no age dimension, and the column name says so."""
        result = lost_years_who(sample_data)
        assert "who_life_expectancy_at_birth" in result.columns
        assert "who_life_expectancy" not in result.columns
        assert "who_age" not in result.columns

    def test_lost_years_who_refuses_an_age_mapping(self, sample_data):
        """Asking WHO an age-specific question raises instead of ignoring it."""
        cols = {"country": "country", "age": "age", "sex": "sex", "year": "year"}
        with pytest.raises(ValueError, match="life expectancy at birth"):
            lost_years_who(sample_data, cols=cols)


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_missing_columns_ssa(self, caplog):
        """Test SSA function with missing required columns."""
        # Missing 'age' column
        df_missing_age = pd.DataFrame({"sex": ["M", "F"], "year": [2020, 2021]})
        with caplog.at_level(logging.WARNING):
            result = lost_years_ssa(df_missing_age)
        # Should return original DataFrame unchanged
        assert result.equals(df_missing_age)

        # Check error message was logged
        assert "No column `age` in the DataFrame" in caplog.text

    def test_missing_columns_who(self, caplog):
        """Test WHO function with missing required columns."""
        # Missing 'country' column
        df_missing_country = pd.DataFrame(
            {"age": [25, 30], "sex": ["M", "F"], "year": [2020, 2021]}
        )
        with caplog.at_level(logging.WARNING):
            result = lost_years_who(df_missing_country)
        # Should return original DataFrame unchanged
        assert result.equals(df_missing_country)

        # Check error message was logged
        assert "No column `country` in the DataFrame" in caplog.text

    def test_empty_dataframe(self):
        """Test functions with empty DataFrame."""
        empty_df = pd.DataFrame()

        # All functions should handle empty DataFrames gracefully
        result_ssa = lost_years_ssa(empty_df)
        result_who = lost_years_who(empty_df)
        result_hld = lost_years_hld(empty_df)

        assert result_ssa.empty
        assert result_who.empty
        assert result_hld.empty

    def test_custom_column_mapping(self):
        """Test functions with custom column names."""
        # Create data with non-standard column names
        df_custom = pd.DataFrame(
            {
                "person_age": [25, 30, 40],
                "gender": ["M", "F", "M"],
                "birth_year": [2020, 2020, 2020],
                "nation": ["USA", "CAN", "MEX"],
            }
        )

        cols_ssa = {"age": "person_age", "sex": "gender", "year": "birth_year"}
        result_ssa = lost_years_ssa(df_custom, cols=cols_ssa)
        assert all(s.startswith("ok") for s in result_ssa["ssa_match_status"])

        cols_who = {"sex": "gender", "year": "birth_year", "country": "nation"}
        result_who = lost_years_who(df_custom, cols=cols_who)
        assert all(s.startswith("ok") for s in result_who["who_match_status"])

    def test_invalid_column_mapping(self, caplog):
        """Test with invalid column mapping."""
        df = pd.DataFrame({"age": [25], "sex": ["M"], "year": [2020]})

        # Map to non-existent column
        invalid_cols = {"age": "nonexistent_age", "sex": "sex", "year": "year"}
        with caplog.at_level(logging.WARNING):
            result = lost_years_ssa(df, cols=invalid_cols)

        # Should return original DataFrame
        assert result.equals(df)

        # Should log error message
        assert "No column `nonexistent_age` in the DataFrame" in caplog.text


class TestDataValidation:
    """Test data validation and edge cases."""

    def test_edge_case_ages(self):
        """Ages the table covers resolve; ages past its top do not."""
        df_edge_ages = pd.DataFrame(
            {
                "age": [0, 1, 119, 200],
                "sex": ["M", "F", "M", "F"],
                "year": [2022] * 4,
                "country": ["USA"] * 4,
            }
        )
        result_ssa = lost_years_ssa(df_edge_ages)
        assert all(s.startswith("ok") for s in list(result_ssa["ssa_match_status"])[:3])
        assert pd.isna(result_ssa["ssa_life_expectancy"].iloc[3])

    def test_missing_age_does_not_return_life_expectancy_at_birth(self):
        """`abs(x - nan)` is nan, which used to make a missing age mean age 0."""
        df = pd.DataFrame(
            {"age": [float("nan")], "sex": ["M"], "year": [2022], "country": ["USA"]}
        )
        row = lost_years_ssa(df).iloc[0]
        assert pd.isna(row["ssa_life_expectancy"])
        assert row["ssa_life_expectancy"] != SSA_2022[("M", 0)]
        assert row["ssa_match_status"] == "cannot match a missing value"

    def test_different_sex_formats(self):
        """Male tokens map to MLE; everything else falls to FMLE."""
        df_sex_variants = pd.DataFrame(
            {
                "sex": ["Male", "Female", "1", "m"],
                "year": [2019] * 4,
                "country": ["USA"] * 4,
            }
        )
        result_who = lost_years_who(df_sex_variants)
        assert list(result_who["who_sex"]) == ["MLE", "FMLE", "MLE", "MLE"]

    def test_old_and_future_years(self):
        """A distant year is answered from the table it came from, and says so."""
        df_edge_years = pd.DataFrame(
            {
                "age": [25, 30, 35],
                "sex": ["M", "F", "M"],
                "year": [1900, 2500, 2019],
                "country": ["USA", "USA", "USA"],
            }
        )

        result_ssa = lost_years_ssa(df_edge_years)
        # The package documents closest-year matching and lost_years_ssa is a
        # counterfactual, so a distant year is still answered -- but the row
        # must name the table year it came from and how far that is.
        assert result_ssa["ssa_life_expectancy"].notna().all()
        assert (result_ssa["ssa_year"] == 2022).all()
        assert (
            "2022 for requested 1900 (122 years away)"
            in (result_ssa["ssa_match_status"].iloc[0])
        )
        assert (
            "2022 for requested 2500 (478 years away)"
            in (result_ssa["ssa_match_status"].iloc[1])
        )
        assert result_ssa["ssa_match_status"].iloc[2].startswith("ok")

        result_who = lost_years_who(df_edge_years)
        expectancies = result_who["who_life_expectancy_at_birth"]
        # Same policy as SSA: answer from the nearest table year, and say which.
        assert expectancies.notna().all()
        # The table spans 2000-2021, so each end clamps to its nearest year.
        assert result_who["who_year"].tolist()[:2] == [2000, 2021]
        assert expectancies.iloc[2] == pytest.approx(76.53, abs=0.005)

    def test_tolerance_can_be_tightened_explicitly(self):
        """Reporting is the default; a caller who wants a hard limit sets one."""
        df = pd.DataFrame({"age": [30], "sex": ["M"], "year": [1900]})
        row = lost_years_ssa(df, year_tolerance=5.0).iloc[0]
        assert pd.isna(row["ssa_life_expectancy"])
        assert "more than 5.0 from 1900" in row["ssa_match_status"]
