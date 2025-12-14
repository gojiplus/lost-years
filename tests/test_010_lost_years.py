"""Tests for lost_years package."""


import pandas as pd
import pytest

from lost_years import lost_years_hld, lost_years_ssa, lost_years_who


class TestLostYears:
    """Test class for lost_years functions."""

    @pytest.fixture
    def sample_data(self):
        """Load sample data for testing."""
        return pd.read_csv("tests/input.csv")

    def test_lost_years_ssa(self, sample_data):
        """Test SSA lost years calculation."""
        result = lost_years_ssa(sample_data)
        assert "ssa_life_expectancy" in result.columns
        assert result.iloc[0].ssa_year >= 2004  # SSA data updated

    def test_lost_years_hld(self, sample_data):
        """Test HLD lost years calculation."""
        result = lost_years_hld(sample_data)
        # HLD requires external data file, so test may return original data if not available
        if "hld_life_expectancy" in result.columns:
            assert "hld_life_expectancy" in result.columns
            assert "hld_year" in result.columns
        else:
            # No HLD data available - function should return original data unchanged
            assert result.shape == sample_data.shape

    def test_lost_years_who(self, sample_data):
        """Test WHO lost years calculation."""
        result = lost_years_who(sample_data)
        assert "who_life_expectancy" in result.columns
        assert result.iloc[0].who_year >= 2003  # WHO data may be updated


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_missing_columns_ssa(self, capsys):
        """Test SSA function with missing required columns."""
        # Missing 'age' column
        df_missing_age = pd.DataFrame({
            "sex": ["M", "F"],
            "year": [2020, 2021]
        })
        result = lost_years_ssa(df_missing_age)
        # Should return original DataFrame unchanged
        assert result.equals(df_missing_age)

        # Check error message was printed
        captured = capsys.readouterr()
        assert "No column `age` in the DataFrame" in captured.out

    def test_missing_columns_who(self, capsys):
        """Test WHO function with missing required columns."""
        # Missing 'country' column
        df_missing_country = pd.DataFrame({
            "age": [25, 30],
            "sex": ["M", "F"],
            "year": [2020, 2021]
        })
        result = lost_years_who(df_missing_country)
        # Should return original DataFrame unchanged
        assert result.equals(df_missing_country)

        # Check error message was printed
        captured = capsys.readouterr()
        assert "No column `country` in the DataFrame" in captured.out

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
        df_custom = pd.DataFrame({
            "person_age": [25, 30, 40],
            "gender": ["M", "F", "M"],
            "birth_year": [2000, 2005, 2010],
            "nation": ["USA", "CAN", "MEX"]
        })

        # Test SSA with custom mapping
        cols_ssa = {"age": "person_age", "sex": "gender", "year": "birth_year"}
        result_ssa = lost_years_ssa(df_custom, cols=cols_ssa)
        assert isinstance(result_ssa, pd.DataFrame)

        # Test WHO with custom mapping
        cols_who = {"age": "person_age", "sex": "gender", "year": "birth_year", "country": "nation"}
        result_who = lost_years_who(df_custom, cols=cols_who)
        assert isinstance(result_who, pd.DataFrame)

    def test_invalid_column_mapping(self, capsys):
        """Test with invalid column mapping."""
        df = pd.DataFrame({
            "age": [25],
            "sex": ["M"],
            "year": [2020]
        })

        # Map to non-existent column
        invalid_cols = {"age": "nonexistent_age", "sex": "sex", "year": "year"}
        result = lost_years_ssa(df, cols=invalid_cols)

        # Should return original DataFrame
        assert result.equals(df)

        # Should print error message
        captured = capsys.readouterr()
        assert "No column `nonexistent_age` in the DataFrame" in captured.out


class TestDataValidation:
    """Test data validation and edge cases."""

    def test_edge_case_ages(self):
        """Test with boundary age values."""
        df_edge_ages = pd.DataFrame({
            "age": [0, 1, 99, 100],
            "sex": ["M", "F", "M", "F"],
            "year": [2020, 2020, 2020, 2020],
            "country": ["USA", "USA", "USA", "USA"]
        })

        # Functions should handle edge ages gracefully
        result_ssa = lost_years_ssa(df_edge_ages)
        result_who = lost_years_who(df_edge_ages)

        assert isinstance(result_ssa, pd.DataFrame)
        assert isinstance(result_who, pd.DataFrame)

    def test_different_sex_formats(self):
        """Test with different sex/gender format variations."""
        # Test various sex code formats
        df_sex_variants = pd.DataFrame({
            "age": [25, 30, 35, 40],
            "sex": ["Male", "Female", "1", "0"],  # Different formats
            "year": [2020, 2020, 2020, 2020],
            "country": ["USA", "USA", "USA", "USA"]
        })

        # Should handle different sex formats
        result_who = lost_years_who(df_sex_variants)
        assert isinstance(result_who, pd.DataFrame)

    def test_old_and_future_years(self):
        """Test with very old and future years."""
        df_edge_years = pd.DataFrame({
            "age": [25, 30, 35],
            "sex": ["M", "F", "M"],
            "year": [1900, 2030, 1950],  # Edge case years
            "country": ["USA", "CAN", "MEX"]
        })

        # Should handle edge case years gracefully
        result_ssa = lost_years_ssa(df_edge_years)
        result_who = lost_years_who(df_edge_years)

        assert isinstance(result_ssa, pd.DataFrame)
        assert isinstance(result_who, pd.DataFrame)
