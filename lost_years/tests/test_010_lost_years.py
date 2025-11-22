"""Tests for lost_years package."""

import pandas as pd
import pytest
from lost_years import lost_years_ssa, lost_years_hld, lost_years_who


class TestLostYears:
    """Test class for lost_years functions."""

    @pytest.fixture
    def sample_data(self):
        """Load sample data for testing."""
        return pd.read_csv('lost_years/tests/input.csv')

    def test_lost_years_ssa(self, sample_data):
        """Test SSA lost years calculation."""
        result = lost_years_ssa(sample_data)
        assert 'ssa_life_expectancy' in result.columns
        assert result.iloc[0].ssa_year == 2004

    def test_lost_years_hld(self, sample_data):
        """Test HLD lost years calculation."""
        result = lost_years_hld(sample_data)
        assert 'hld_life_expectancy' in result.columns
        assert result.iloc[0].hld_year1 == 2003

    def test_lost_years_who(self, sample_data):
        """Test WHO lost years calculation."""
        result = lost_years_who(sample_data)
        assert 'who_life_expectancy' in result.columns
        assert result.iloc[0].who_year == 2003
