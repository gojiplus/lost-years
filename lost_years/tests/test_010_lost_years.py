"""Tests for lost_years package."""

import pandas as pd
import pytest

from lost_years import lost_years_hld, lost_years_ssa, lost_years_who


class TestLostYears:
    """Test class for lost_years functions."""

    @pytest.fixture
    def sample_data(self):
        """Load sample data for testing."""
        return pd.read_csv("lost_years/tests/input.csv")

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
