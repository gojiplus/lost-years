# Command Line Interface

## Installation

```bash
pip install lost-years
```

After installation, three command-line tools are available:
- `lost_years_ssa` - US Social Security Administration data
- `lost_years_hld` - Human Life-Table Database (international)
- `lost_years_who` - World Health Organization data

## Basic Usage

All commands follow a similar pattern:

```bash
lost_years_[source] input.csv -o output.csv
```

Where:
- `[source]` is `ssa`, `hld`, or `who`
- `input.csv` is your input file with required columns
- `output.csv` is the output file with appended life expectancy data

## Commands

### lost_years_ssa

Calculate expected years lost using US SSA data:

```bash
lost_years_ssa input.csv -o output.csv
```

**Required columns in input file:**
- `age` - Age at death (0-119)
- `sex` - Sex (M/F)
- `year` - Year of death

**Options:**
- `-a, --age` - Column name for age (default: `age`)
- `-s, --sex` - Column name for sex (default: `sex`)
- `-y, --year` - Column name for year (default: `year`)
- `-o, --output` - Output file path

**Output columns added:**
- `ssa_age` - Matched age used
- `ssa_year` - Matched year used
- `ssa_life_expectancy` - Expected years remaining

### lost_years_hld

Calculate expected years lost using international HLD data:

```bash
lost_years_hld input.csv -o output.csv
```

**Required columns in input file:**
- `country` - Country code (e.g., BRA, CHE)
- `age` - Age at death
- `sex` - Sex (M/F)
- `year` - Year of death

**Options:**
- `-c, --country` - Column name for country (default: `country`)
- `-a, --age` - Column name for age (default: `age`)
- `-s, --sex` - Column name for sex (default: `sex`)
- `-y, --year` - Column name for year (default: `year`)
- `-o, --output` - Output file path
- `--download-hld` - Download latest HLD data

**Output columns added:**
- `hld_country` - Country code
- `hld_age` - Matched age
- `hld_year1` - Matched year
- `hld_life_expectancy` - Expected years remaining
- Additional columns for sub-populations if available

### lost_years_who

Calculate expected years lost using WHO data:

```bash
lost_years_who input.csv -o output.csv
```

**Required columns in input file:**
- `country` - Country code
- `age` - Age at death
- `sex` - Sex (M/F)
- `year` - Year of death

**Options:**
- `-c, --country` - Column name for country (default: `country`)
- `-a, --age` - Column name for age (default: `age`)
- `-s, --sex` - Column name for sex (default: `sex`)
- `-y, --year` - Column name for year (default: `year`)
- `-o, --output` - Output file path

**Output columns added:**
- `who_country` - Country code
- `who_age` - Matched age
- `who_year` - Matched year
- `who_sex` - Sex code used
- `who_life_expectancy` - Expected years remaining

## Examples

### Example 1: US Data

Input file `us_deaths.csv`:
```csv
age,sex,year
65,M,2020
45,F,2019
80,M,2018
```

Command:
```bash
lost_years_ssa us_deaths.csv -o us_deaths_with_life_exp.csv
```

### Example 2: International Comparison

Input file `international.csv`:
```csv
country,age,sex,year
BRA,65,M,2015
CHE,65,M,2015
JPN,65,M,2015
```

Command:
```bash
lost_years_hld international.csv -o comparison.csv
```

### Example 3: Custom Column Names

Input file with non-standard column names:
```csv
nation,age_at_death,gender,death_year
USA,70,M,2020
```

Command:
```bash
lost_years_ssa input.csv \
  -a age_at_death \
  -s gender \
  -y death_year \
  -o output.csv
```

## Data Coverage

### SSA (United States)
- Years: 1900-2100 (projected)
- Ages: 0-119
- Sex: Male/Female

### HLD (International)
- Countries: 40+ countries
- Years: Varies by country (typically 1950-2020)
- Ages: 0-110+
- Additional dimensions for some countries

### WHO (Global)
- Countries: 180+ countries
- Years: 2000-2019
- Ages: 5-year bands
- Sex: Male/Female/Both

## Notes

- The tools automatically match to the closest available year and age if exact matches aren't found
- The matched values are included in output columns so you can verify what data was used
- HLD may return multiple rows per input if sub-populations are available
- For US-specific analysis, SSA provides the most detailed data
- For international comparisons, use HLD or WHO for consistency