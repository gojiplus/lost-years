"""Type definitions and data structures for lost_years package."""

from dataclasses import dataclass

# Type aliases for common data types
type ColumnMapping = dict[str, str]
type DataSourceColumns = list[str]


@dataclass(slots=True, frozen=True)
class ColumnConfig:
    """Configuration for column mappings in DataFrames.

    Attributes:
        age: Column name for age data
        sex: Column name for sex/gender data
        year: Column name for year data
        country: Column name for country data (optional)
    """

    age: str = "age"
    sex: str = "sex"
    year: str = "year"
    country: str = "country"

    def to_dict(self) -> ColumnMapping:
        """Convert to dictionary format for backwards compatibility."""
        return {"age": self.age, "sex": self.sex, "year": self.year, "country": self.country}


@dataclass(slots=True, frozen=True)
class DataSourceConfig:
    """Configuration for a life expectancy data source.

    Attributes:
        name: Human readable name of the data source
        file_path: Path to the data file
        columns: List of required columns
        compression: Compression type if any
    """

    name: str
    file_path: str
    columns: DataSourceColumns
    compression: str | None = None


@dataclass(slots=True)
class LifeExpectancyResult:
    """Result from life expectancy calculation.

    Attributes:
        source_age: Age from source data.
        source_year: Year from source data.
        life_expectancy: Calculated life expectancy.
        data_source: Which data source was used.
        source_country: Country from source data (if applicable).
    """

    source_age: int
    source_year: int
    life_expectancy: float
    data_source: str
    source_country: str | None = None
