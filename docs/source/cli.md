# Command Line Interface

## Installation

```bash
pip install lost-years
```

After installation, four command-line tools are available:
- `lost_years` - install and inspect the life tables the lookups read
- `lost_years_ssa` - US Social Security Administration data
- `lost_years_hld` - Human Life-Table Database (international)
- `lost_years_who` - World Health Organization data

## lost_years: managing the data

Only the SSA table ships in the wheel. HLD and WHO are downloaded on request:

```bash
lost_years update --source all      # or hld / who / ssa
lost_years status                   # what is installed, and has upstream moved?
lost_years sources                  # where each table comes from, and on what terms
```

### lost_years update

Downloads to a scratch directory, builds a typed Parquet table, checks it
against the declared Arrow schema, a row-count contract and the published
life-expectancy figures, and **only then** swaps it into place. A candidate
that fails any check is discarded and the table you already had is untouched.

**Options:**
- `--source {hld,ssa,who,all}` - which source to update (default: `all`)
- `--from-file PATH` - build from a local artifact instead of downloading.
  ssa.gov refuses automated clients from some networks; save the page in a
  browser and pass it here to run exactly the same parse, validation and swap.
- `--output DIR` - install somewhere other than the per-user data directory

Tables land in the per-user data directory, which `$LOST_YEARS_DATA_DIR`
overrides and `lost_years status` prints.

### lost_years status

Reports, per source: what is installed, which upstream release it is, when it
was fetched, how many rows it has, and what upstream is publishing now.

```text
source  state     installed    upstream     rows
hld     stale     2025-04-07   2026-02-03   2,182,429
ssa     unknown   2022         -            120
who     current   2021         2021         12,936
```

`--offline` reports what is installed without contacting upstream. A table
whose SHA-256 no longer matches its manifest is reported as `damaged`.

### lost_years sources

Prints the registry: home page, download URL, license and filename for each
source. Read it before redistributing anything derived from these tables --
HLD in particular carries no redistribution grant.

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
- `ssa_match_status` - `ok`, or why no figure was returned

The shipped table is the 2022 period life table. A distant year is still
answered from it -- `lost_years_ssa` is a counterfactual -- but
`ssa_match_status` always names the table year and how far the reach was. A
missing age returns a missing life expectancy and a reason, rather than the
first number in the table.

### lost_years_hld

Calculate expected years lost using international HLD data:

```bash
lost_years_hld input.csv -o output.csv
```

**Required columns in input file:**
- `country` - ISO-3166-1 alpha-3 country code (e.g., BRA, CHE), matched exactly
- `age` - Age at death
- `sex` - Sex (M/F)
- `year` - Year of death

**Options:**
- `-c, --country` - Column name for country (default: `country`)
- `-a, --age` - Column name for age (default: `age`)
- `-s, --sex` - Column name for sex (default: `sex`)
- `-y, --year` - Column name for year (default: `year`)
- `-o, --output` - Output file path
- `--subpopulations` - Emit one row per sub-population instead of the national total
- `--year-tolerance N` - Accept a life table whose period misses the year by up to N years
- `--no-quarantine` - Serve life tables whose recalculated and published e(x) disagree

**Output columns added:**
- `hld_country`, `hld_sex` - Matched country and sex
- `hld_year1`, `hld_year2` - Period the matched life table covers
- `hld_age`, `hld_age_interval` - Matched age interval (`99` marks the open top interval)
- `hld_life_expectancy` - Expected years remaining at `hld_age`
- `hld_ref_id`, `hld_version`, `hld_type_lt` - Which HLD life table was used
- `hld_ex_discrepancy` - Largest gap between recalculated and published e(x) in that table
- `hld_n_candidates` - How many equally eligible life tables the tie-break chose between
- `hld_match_status` - `ok`, or why no figure was returned
- `hld_region`, `hld_residence`, `hld_ethnicity`, `hld_socdem` - Sub-population codes (`0` is the total)

The selection rule is documented in the [data dictionary](data-dictionary.md).

### lost_years_who

Look up WHO life expectancy at birth:

```bash
lost_years_who input.csv -o output.csv
```

**Required columns in input file:**
- `country` - Country code
- `sex` - Sex (M/F)
- `year` - Year of death

There is no age option. The WHO table is GHO indicator WHOSIS_000001, life
expectancy at birth, and has no age dimension; use `lost_years_hld` for
remaining life expectancy at a given age.

**Options:**
- `-c, --country` - Column name for country (default: `country`)
- `-s, --sex` - Column name for sex (default: `sex`)
- `-y, --year` - Column name for year (default: `year`)
- `-o, --output` - Output file path

**Output columns added:**
- `who_country` - Country code
- `who_year` - Matched year
- `who_sex` - Sex code used
- `who_life_expectancy_at_birth` - Life expectancy at birth
- `who_match_status` - `ok`, or why no figure was returned

## Examples

### Example 1: US Data

Input file `us_deaths.csv`:
```text
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
```text
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
```text
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
- Ships in the wheel; everything else is installed with `lost_years update`
- Years: 2022 (one period life table)
- Ages: 0-119, single years
- Sex: Male/Female

### HLD (International)
- Countries: 142 in the file; 133 have a whole-country total-population table
- Years: 1751-2023, varying by country and often as multi-year periods
- Ages: single years or abridged intervals, depending on the source table
- Sub-populations (regions, urban/rural, ethnicity, socio-demographic groups)
  available with `--subpopulations`

### WHO (Global)
- Countries: 196
- Years: 2000-2021
- Ages: none -- life expectancy at birth only
- Sex: Male/Female/Both

## Notes

- SSA and WHO match to the closest available year and age and always report the
  distance in `*_match_status`; pass `--year-tolerance`/`year_tolerance` to
  refuse a match beyond a limit instead
- HLD matches on the period a life table actually covers, and returns nothing
  for a country-year no table covers unless `--year-tolerance` is given
- The matched values are included in output columns so you can verify what data
  was used
- HLD returns one row per input row unless `--subpopulations` is given
- For US-specific analysis, SSA provides the most detailed data
- For international comparisons, use HLD or WHO for consistency