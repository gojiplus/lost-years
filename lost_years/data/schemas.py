#!/usr/bin/env python3
"""
Data schemas for lost_years package data sources.

This module defines the expected schema for each data source:
- SSA: US Social Security Administration life tables
- WHO: World Health Organization life expectancy data
- HLD: Human Life-Table Database from lifetable.de
"""

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass
class SSASchema:
    """Schema for SSA (Social Security Administration) life table data.

    Source: https://www.ssa.gov/oact/STATS/table4c6.html
    Format: CSV with age-specific mortality and life expectancy data
    """

    # Required columns
    REQUIRED_COLUMNS = [
        "age",  # int: Exact age (0-119)
        "male_death_prob",  # float: Male death probability q(x)
        "male_n_lives",  # float: Male number of lives l(x)
        "male_life_expectancy",  # float: Male life expectancy e(x)
        "female_death_prob",  # float: Female death probability q(x)
        "female_n_lives",  # float: Female number of lives l(x)
        "female_life_expectancy",  # float: Female life expectancy e(x)
        "year",  # int: Data year (e.g., 2022)
    ]

    # Data types
    DTYPES = {
        "age": "int32",
        "male_death_prob": "float64",
        "male_n_lives": "float64",
        "male_life_expectancy": "float64",
        "female_death_prob": "float64",
        "female_n_lives": "float64",
        "female_life_expectancy": "float64",
        "year": "int32",
    }

    # Validation rules
    AGE_RANGE = (0, 119)  # Ages 0-119
    YEAR_RANGE = (2000, 2030)  # Reasonable year range
    PROB_RANGE = (0.0, 1.0)  # Death probabilities 0-1
    LIVES_RANGE = (0.0, 100000.0)  # Number of lives 0-100k
    LE_RANGE = (0.0, 100.0)  # Life expectancy 0-100 years

    @classmethod
    def validate(cls, df: pd.DataFrame) -> dict[str, Any]:
        """Validate SSA data against schema."""
        issues = []

        # Check required columns
        missing_cols = set(cls.REQUIRED_COLUMNS) - set(df.columns)
        if missing_cols:
            issues.append(f"Missing columns: {missing_cols}")

        # Check age range
        if "age" in df.columns:
            invalid_ages = df[(df["age"] < cls.AGE_RANGE[0]) | (df["age"] > cls.AGE_RANGE[1])]
            if not invalid_ages.empty:
                issues.append(f"Invalid ages: {invalid_ages['age'].tolist()}")

        # Check year range
        if "year" in df.columns:
            invalid_years = df[(df["year"] < cls.YEAR_RANGE[0]) | (df["year"] > cls.YEAR_RANGE[1])]
            if not invalid_years.empty:
                issues.append(f"Invalid years: {invalid_years['year'].unique().tolist()}")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "row_count": len(df),
            "column_count": len(df.columns),
        }


@dataclass
class WHOSchema:
    """Schema for WHO (World Health Organization) life expectancy data.

    Source: WHO Global Health Observatory API
    Format: Compressed CSV with global country life expectancy data
    """

    # Required columns (simplified from WHO API response)
    REQUIRED_COLUMNS = [
        "country_code",  # str: 3-letter ISO country code (e.g., 'USA')
        "country_name",  # str: Country display name
        "year",  # int: Data year
        "sex_code",  # str: Sex code ('MLE', 'FMLE', 'BTSX')
        "life_expectancy",  # float: Life expectancy value
        "low_ci",  # float: Lower confidence interval
        "high_ci",  # float: Upper confidence interval
    ]

    # Data types
    DTYPES = {
        "country_code": "string",
        "country_name": "string",
        "year": "int32",
        "sex_code": "string",
        "life_expectancy": "float64",
        "low_ci": "float64",
        "high_ci": "float64",
    }

    # Validation rules
    YEAR_RANGE = (1990, 2030)  # WHO data year range
    LE_RANGE = (20.0, 90.0)  # Reasonable life expectancy range
    VALID_SEX_CODES = {"MLE", "FMLE", "BTSX"}  # Male, Female, Both sexes

    @classmethod
    def validate(cls, df: pd.DataFrame) -> dict[str, Any]:
        """Validate WHO data against schema."""
        issues = []

        # Check required columns
        missing_cols = set(cls.REQUIRED_COLUMNS) - set(df.columns)
        if missing_cols:
            issues.append(f"Missing columns: {missing_cols}")

        # Check sex codes
        if "sex_code" in df.columns:
            invalid_sex = set(df["sex_code"].unique()) - cls.VALID_SEX_CODES
            if invalid_sex:
                issues.append(f"Invalid sex codes: {invalid_sex}")

        # Check life expectancy range
        if "life_expectancy" in df.columns:
            invalid_le = df[
                (df["life_expectancy"] < cls.LE_RANGE[0])
                | (df["life_expectancy"] > cls.LE_RANGE[1])
            ]
            if not invalid_le.empty:
                issues.append(f"Invalid life expectancy values: {len(invalid_le)} rows")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "row_count": len(df),
            "column_count": len(df.columns),
            "countries": df["country_code"].nunique() if "country_code" in df.columns else 0,
            "years": sorted(df["year"].unique().tolist()) if "year" in df.columns else [],
        }


@dataclass
class HLDSchema:
    """Schema for HLD (Human Life-Table Database) data.

    Source: https://www.lifetable.de/
    Format: Large CSV with complete life table data for 142 countries, 1751-2023
    """

    # Required columns (subset of 21 total columns)
    REQUIRED_COLUMNS = [
        "Country",  # str: 3-letter country code
        "Year1",  # int: Data year
        "Sex",  # int: Sex code (1=Male, 2=Female)
        "Age",  # int: Exact age
        "e(x)",  # float: Life expectancy at age x
        "m(x)",  # float: Central death rate
        "q(x)",  # float: Probability of death
        "l(x)",  # float: Number surviving to age x
    ]

    # Data types
    DTYPES = {
        "Country": "string",
        "Year1": "int32",
        "Sex": "int32",
        "Age": "int32",
        "e(x)": "float64",
        "m(x)": "float64",
        "q(x)": "float64",
        "l(x)": "float64",
    }

    # Validation rules
    YEAR_RANGE = (1750, 2030)  # Historical range
    AGE_RANGE = (0, 111)  # Age range
    SEX_CODES = {1, 2}  # 1=Male, 2=Female
    LE_RANGE = (0.0, 100.0)  # Life expectancy range

    @classmethod
    def validate(cls, df: pd.DataFrame) -> dict[str, Any]:
        """Validate HLD data against schema."""
        issues = []

        # Check required columns (allow subset)
        available_required = [col for col in cls.REQUIRED_COLUMNS if col in df.columns]
        if len(available_required) < 4:  # Need at least country, year, sex, life expectancy
            issues.append(f"Too few required columns. Found: {available_required}")

        # Check sex codes
        if "Sex" in df.columns:
            invalid_sex = set(df["Sex"].unique()) - cls.SEX_CODES
            if invalid_sex:
                issues.append(f"Invalid sex codes: {invalid_sex}")

        # Check life expectancy range
        if "e(x)" in df.columns:
            invalid_le = df[(df["e(x)"] < cls.LE_RANGE[0]) | (df["e(x)"] > cls.LE_RANGE[1])]
            if not invalid_le.empty:
                issues.append(f"Invalid life expectancy values: {len(invalid_le)} rows")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "row_count": len(df),
            "column_count": len(df.columns),
            "countries": df["Country"].nunique() if "Country" in df.columns else 0,
            "years": sorted(df["Year1"].unique().tolist()) if "Year1" in df.columns else [],
        }


def validate_data_file(source: str, file_path: str) -> dict[str, Any]:
    """Validate a data file against its schema.

    Args:
        source: Data source ('ssa', 'who', 'hld')
        file_path: Path to data file

    Returns:
        Validation results dict
    """
    try:
        # Load data based on file extension
        if file_path.endswith(".gz"):
            df = pd.read_csv(file_path, compression="gzip")
        else:
            df = pd.read_csv(file_path)

        # Validate against appropriate schema
        match source.lower():
            case "ssa":
                return SSASchema.validate(df)
            case "who":
                return WHOSchema.validate(df)
            case "hld":
                return HLDSchema.validate(df)
            case _:
                return {"valid": False, "issues": [f"Unknown source: {source}"]}

    except Exception as e:
        return {"valid": False, "issues": [f"Error reading file: {e}"]}


if __name__ == "__main__":
    """Test schema validation on current data files."""
    from pathlib import Path

    data_dir = Path(__file__).parent

    # Test each data source
    sources = {
        "ssa": data_dir / "ssa" / "ssa.csv",
        "who": data_dir / "who" / "who-lt.csv.gz",
        "hld": data_dir / "hld" / "hld.csv.gz",
    }

    for source, file_path in sources.items():
        if file_path.exists():
            print(f"\n=== {source.upper()} Schema Validation ===")
            result = validate_data_file(source, str(file_path))
            print(f"Valid: {result['valid']}")
            if result["issues"]:
                print(f"Issues: {result['issues']}")
            print(f"Rows: {result.get('row_count', 'N/A')}")
            print(f"Columns: {result.get('column_count', 'N/A')}")
        else:
            print(f"\n{source.upper()}: File not found: {file_path}")
