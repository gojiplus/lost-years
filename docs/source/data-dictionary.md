# Data dictionary

What the packaged tables contain, and — for HLD, where one country-year is
often covered by several published life tables — exactly which row a lookup
returns and why.

## HLD (Human Life-Table Database)

**Source.** The pooled HLD file from [lifetable.de](https://www.lifetable.de/),
release 07.04.2025, packaged as `lost_years/data/hld/hld.csv.gz`. The upstream
codebook is `lost_years/data/hld/formats.pdf`.

**Unit of observation of the file.** One row is *one age interval of one
published life table*: country x sub-population x source publication x version
x reference period x table type x sex x age. 2,182,429 rows, 142 countries,
1751-2023.

**Unit of observation of a lookup.** One row per input row, from one life
table. HLD is not an estimate per country-year, so this is a choice the package
makes, not a property of the data; the rule is below and
`hld_n_candidates` reports how many tables the last step of it chose between.

### Columns read

| Column | Meaning | Notes |
|---|---|---|
| `Country` | ISO-3166-1 alpha-3 code | matched exactly, case-insensitively |
| `Region` | principal subdivision | `0` = whole country |
| `Residence` | urban / rural | `0` = total population |
| `Ethnicity` | ethnicity, religion or race | `0` = total population |
| `SocDem` | socio-demographic group | `0` = total population |
| `Version` | HLD's revision counter for one source and year | |
| `Ref-ID` | source code, `NNNN.PP` | `NNNN` publication, `PP` place within it |
| `Year1`, `Year2` | first and last year of the period | equal for a single-year table |
| `TypeLT` | 1 complete, 2 abridged-from-1, 4 abridged-from-published | 2 is dropped |
| `Sex` | 1 male, 2 female | exposed as `M` / `F` |
| `Age` | lower bound of the age interval | |
| `AgeInt` | length of the age interval | `99` = open-ended top interval |
| `e(x)` | life expectancy at exact `Age`, recalculated by HLD | the value returned |
| `e(x)Orig` | life expectancy as printed in the original publication | `.` = missing |

### Known upstream and packaging defects

| Defect | Extent | Handling |
|---|---|---|
| Sub-population codes written as `0.0`, `10.0` ... by a float round-trip in packaging | 181,953 `Region` values | codes are read as text and a trailing `.0` is stripped; a naive `== '0'` filter keeps 550,429 national rows, normalising keeps 717,457 |
| `Region` written as the literal `NA` upstream, read as missing | 1,334 rows, 7 countries | treated as whole-country: the codebook has no "region unknown" code and every such row is a national table (NIU, KIR, NRU, and the single-year national tables for HUN 2018, IRN 2004, ISR 2013-17, SWE 2019) |
| Negative `AgeInt` | 37 rows, all sub-national (ITA, KOR) | cannot define an interval, so dropped |
| `e(x)` and `e(x)Orig` disagree by more than 2 years | 357 national life tables, 15,306 rows | quarantined, see below |

### The selection rule

For a query `(country, year, sex, age)`, in order:

1. **Whole country, total population.** `Region == Residence == Ethnicity ==
   SocDem == '0'`, after the normalisation above. `subpopulations=True` lifts
   this and returns one row per sub-population instead.
2. **Drop `TypeLT == 2`.** Type 2 is HLD's own abridgement of the type 1
   complete table from the same source, so it never carries information the
   finer table does not already have.
3. **Quarantine tables that fail their own cross-check.** `e(x)` and
   `e(x)Orig` are independent computations of the same quantity, so a large gap
   means at least one is wrong and neither can be trusted. A table is dropped
   when the gap exceeds 2 years anywhere in it. This is what catches ARG 1980
   Ref-ID 1042.01, whose recalculated e(0) of 79.11 contradicts its own
   published 65.48 — implying 24,014 men per 100,000 still alive at 95. The
   error runs both ways: YUG 1980-82 Ref-ID 3950.01 prints `e(x)Orig` of 80.00
   at age 93 against a recalculated 1.81, a slip for 1.80. Pass
   `max_ex_discrepancy=None` to serve them anyway.

   The quarantine changes real answers. Three national tables cover France in
   2010; the 2010-2012 one recalculates female life expectancy at birth to
   81.51 against its own published 84.84. Dropping it leaves 84.70, against
   INSEE's published 84.7.
4. **Period containment.** Keep life tables with `Year1 <= year <= Year2`.
   2,482 country-years in HLD are reachable only through a multi-year period
   table, so containment is required rather than optional. A year no table
   covers returns nothing; `year_tolerance` reaches to the nearest period and
   records the distance in `hld_match_status`.
5. **Narrowest period.** Of those, keep the tables with the smallest
   `Year2 - Year1`, so a 1980 table beats a 1976-1980 table for 1980.
6. **Age interval.** Keep the row whose interval `[Age, Age + AgeInt)` contains
   the requested age. Many HLD tables are abridged, so age 22 is answered from
   the interval starting at 20; `hld_age` and `hld_age_interval` report which.
7. **Tie-break convention.** Highest `Version`, then highest `Ref-ID`, then
   latest `Year1`, then lowest `TypeLT`. Version is HLD's own revision counter,
   so the highest is the most revised table; Ref-ID rises as sources are added,
   so the highest is the most recently added source. The last two keys exist
   only to make the order total. About 17% of country-year cells reach this
   step with more than one candidate — median disagreement 0.38 years, but 78
   cells disagree by more than 2 — so `hld_n_candidates` reports the count
   rather than hiding it.

### What each filter costs

| Stage | Rows |
|---|---|
| read from `hld.csv.gz` | 2,182,429 |
| whole country, total population | 717,457 |
| drop `TypeLT == 2` | 600,113 |
| quarantine | 584,807 |

142 countries appear in the file; 133 have a whole-country total-population
table at all, and 129 have one that survives the quarantine. **BFA, ETH, GHA,
GMB, GNB, MOZ, PSE, TZA and ZMB** have only sub-national or sub-population
tables, and **ARE, ASM, PAK and THA** have only tables that fail the
cross-check. All thirteen return `hld_match_status` of "no eligible life table
for country" rather than a sub-population figure passed off as the country.

### Output columns

| Column | Meaning |
|---|---|
| `hld_country`, `hld_sex` | matched country and sex |
| `hld_year1`, `hld_year2` | period the matched life table covers |
| `hld_age`, `hld_age_interval` | matched age interval; `99` is the open top interval |
| `hld_life_expectancy` | `e(x)` at `hld_age` |
| `hld_ref_id`, `hld_version`, `hld_type_lt` | which life table was used |
| `hld_ex_discrepancy` | largest absolute gap between `e(x)` and `e(x)Orig` in that table |
| `hld_n_candidates` | how many equally eligible tables the tie-break chose between |
| `hld_match_status` | `ok`, `ok: nearest period, N year(s) away`, or the reason nothing was returned |
| `hld_region`, `hld_residence`, `hld_ethnicity`, `hld_socdem` | sub-population codes; `0` is the total |

## SSA (US Social Security Administration)

`lost_years/data/ssa/ssa.csv`: the 2022 period life table, single years of age
0-119, male and female. One row per age.

Age is matched to within 1 year of age and calendar year to within 5 years;
past either, the lookup returns nothing and says so in `ssa_match_status`.
Five years is chosen because US life expectancy normally moves 0.1-0.2 years
per calendar year, so a five-year reach costs under a year of `e(x)` — and the
2.4-year fall from 2019 to 2021 is why the reach is not longer.

## WHO

`lost_years/data/who/who.csv.gz`: indicator WHOSIS_000001, **life expectancy at
birth**, 196 countries, 2000-2021, sexes `MLE` / `FMLE` / `BTSX`. One row per
country, year and sex.

There is no age dimension. `lost_years_who` therefore takes no age input,
returns `who_life_expectancy_at_birth`, and raises `ValueError` if an `age`
mapping is passed. Year is matched to within 5 years.
