# Examples

This section contains practical examples demonstrating how to use the `lost_years` package to calculate expected years lost using different data sources.

## Overview

The examples showcase the three main functions of the package:

- **`lost_years_ssa`**: Calculate expected years lost using US Social Security Administration data
- **`lost_years_hld`**: Calculate expected years lost using international Human Life-Table Database 
- **`lost_years_who`**: Calculate expected years lost using WHO life expectancy data

## Available Examples

```{toctree}
:maxdepth: 1

examples/example
examples/corona_virus
examples/corona_virus_fr
examples/corona_virus_fr_daily
```

### Basic Usage Example
The basic example demonstrates simple usage with sample data across different countries and demographics.

### COVID-19 Analysis Examples
The coronavirus examples show real-world applications analyzing the impact of COVID-19 on life expectancy across different countries and time periods:

- **corona_virus.ipynb**: General COVID-19 impact analysis
- **corona_virus_fr.ipynb**: Focused analysis on France
- **corona_virus_fr_daily.ipynb**: Daily analysis for France

These examples use real COVID-19 mortality data to demonstrate practical applications of the lost years calculations.

## Data Sources

The examples use data from:
- CDC COVID-19 mortality data
- WHO life expectancy statistics
- SSA actuarial tables
- HLD international life tables

All data files are included in the `data/` subdirectory for reproducibility.