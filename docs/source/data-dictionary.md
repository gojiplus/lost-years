# Data dictionary

What each table contains, column by column, where it came from, and — for HLD,
where one country-year is often covered by several published life tables —
exactly which row a lookup returns and why.

## How the tables get onto your machine

Only **SSA** ships inside the wheel: a US federal work in the public domain,
10 KB, so US lookups work offline the moment the package is installed. **HLD**
and **WHO** are downloaded on request:

```bash
lost_years update --source all      # or hld / who / ssa
lost_years status                   # what is installed, and has upstream moved?
lost_years sources                  # where each table comes from, and on what terms
```

HLD is not shipped because lifetable.de asks that users fetch their own copy
("Please do not pass your copy of these data to other users. Rather refer them
to the HLD website, where they may download the data for themselves"). WHO is
not shipped because a packaged copy is stale the day WHO publishes a revision
and nothing in the wheel would say so.

Tables are written to the per-user data directory, overridable with
`$LOST_YEARS_DATA_DIR`; `lost_years status` prints the path. A downloaded table
always takes precedence over a shipped one.

### What an update does

1. **Download to a scratch directory.** A transfer that stops short of the
   announced `Content-Length` is an error, not a smaller file.
2. **Build** a typed Parquet table with an explicit Arrow schema.
3. **Validate** the candidate: the schema must match field for field, including
   types and nullability; the row count must not be below the release the
   package was tested against, because these databases only grow; and the
   values have to pass the source's own checks (below).
4. **Swap atomically.** The candidate is written under a temporary name *in the
   destination directory* and renamed into place, so a reader sees either the
   old table or the new one. **A candidate that fails any check is not
   installed and the previous table is untouched.**

### What each source is checked against

| Source | Check |
|---|---|
| HLD | US male life expectancy at birth must come out at 76.22 / 76.31 / 74.19 / 73.55 for 2018-2021, through the selection rule below, against NCHS's published 76.2 / 76.3 / 74.2 / 73.5. Plus: one row per life table and age in the national table, and at least 90% of rows carrying a published `e(x)` for the quarantine to mean anything. |
| SSA | Complete single years of age from 0; life expectancy falling with age for both sexes; life expectancy at birth in 60-95 years; women outliving men at every age. SSA is itself the publisher, so there is no external oracle — what is checked is that the table has the structure a period life table must have. |
| WHO | At least 180 countries; every value in 15-100 years; the both-sexes figure between the male and female ones for 99% of country-years; women outliving men in at least 95% of them. The last check is the asymmetric one: exchanging the sex labels leaves the both-sexes test passing and only this notices. |

### Provenance manifest

Every derived table has a `<name>.parquet.manifest.json` beside it:

| Field | Meaning |
|---|---|
| `source`, `title`, `home_url` | which database, and where to read its terms |
| `source_url` | the URL the release is published at |
| `license` | redistribution terms |
| `upstream_release` | upstream's own identifier — HLD's release date, SSA's and WHO's table year |
| `built_from` | `download`, or the local path when `--from-file` was used |
| `fetched_at` | UTC timestamp of the build |
| `rows`, `sha256` | row count and digest of the table |
| `raw_sha256` | digest of the raw artifact it was built from |
| `schema` | every field's name, Arrow type and nullability |
| `build_notes` | source-specific facts, e.g. how many upstream lines could not be read |

`lost_years status` re-digests the installed table and reports `damaged` when it
no longer matches its manifest.

---

## HLD (Human Life-Table Database)

**Source.** The pooled file at
`https://www.lifetable.de/File/GetDocument/data/hld.zip`, a single ZIP holding
one bare CSV named `res` (21 columns, 202 MB). The upstream codebook is
archived at `data/hld/source/formats.pdf`; the raw archive this repository
builds from is `data/hld/source/hld.zip`.

**Release identifier.** The modification time of the `res` member inside the
archive: the release lifetable.de labels 07.04.2025 carries `2025-04-07`.
Taking it from the artifact rather than from the page it was linked on means
the manifest describes the file that was actually built. `lost_years status`
compares it against the newest date on
[lifetable.de/Data/WhatsNew](https://www.lifetable.de/Data/WhatsNew).

**Terms.** No affirmative redistribution grant. Cite the HLD and send others to
the website.

**Unit of observation of the file.** One row is *one age interval of one
published life table*: country × sub-population × source publication × version
× reference period × table type × sex × age. **2,182,429 rows, 45,330 life
tables, 142 countries, 1751-2024.**

**Unit of observation of a lookup.** One row per input row, from one life table.
HLD is not an estimate per country-year, so this is a choice the package makes,
not a property of the data; the rule is below and `hld_n_candidates` reports how
many tables the last step of it chose between.

### Columns of `hld.parquet`

The derived table keeps the 15 of 21 upstream columns a lookup needs, adds two
derived ones, and drops the other life-table functions — m(x), q(x), l(x),
d(x), L(x), T(x) — which play no part in reading a life expectancy off a table.

| Column | Arrow type | Unit / universe | Value set | Missing | Upstream field |
|---|---|---|---|---|---|
| `country` | `dictionary<string>` | one country or area | 142 ISO 3166-1 alpha-3 codes (or HLD extensions) | never | `Country` |
| `region` | `dictionary<string>` | principal subdivision | `0` = whole country; 96 other codes | never (see repairs) | `Region` |
| `residence` | `dictionary<string>` | urban / rural split | `0` = total population; 7 others | never | `Residence` |
| `ethnicity` | `dictionary<string>` | ethnicity, religion or race | `0` = total population; 34 others | never | `Ethnicity` |
| `socdem` | `dictionary<string>` | socio-demographic group | `0` = total population; 3 others | never | `SocDem` |
| `version` | `int8` | HLD's revision counter within one source and year | 1-3 | never | `Version` |
| `ref_id` | `dictionary<string>` | source publication | `NNNN.PP`: `NNNN` the publication, `PP` the place within it; 13,809 values | never | `Ref-ID` |
| `ref_id_sort` | `float64` | `ref_id` as a number, so the tie-break orders `9.01` below `1042.01` | derived | when `ref_id` is not numeric (none in this release) | derived |
| `year1` | `int16` | first calendar year the table covers | 1751-2023 | never | `Year1` |
| `year2` | `int16` | last calendar year covered; equals `year1` for a single-year table | 1760-2024 | never | `Year2` |
| `type_lt` | `int8` | how the table was produced | `1` complete recalculated, `2` abridged from the recalculated complete table, `4` abridged from a published abridged table | never | `TypeLT` |
| `sex` | `dictionary<string>` | sex | `M`, `F` | never | `Sex` (1 male, 2 female) |
| `age` | `int16` | lower bound of the age interval, exact years | 0-119 | never | `Age` |
| `age_interval` | `int16` | length of the age interval, years | 1-15, and the sentinels below | never | `AgeInt` |
| `life_expectancy` | `float64` | remaining years at exact `age`, recalculated by HLD from l(x), d(x) or q(x); radix 100,000 | 0-100 | never (rows without it are dropped) | `e(x)` |
| `life_expectancy_published` | `float64` | the same quantity as printed in the original publication | 0-100 | 1,067 rows; upstream writes `.` | `e(x)Orig` |
| `ex_discrepancy` | `float64` | largest `\|e(x) − e(x)Orig\|` anywhere in *this row's own life table* | ≥ 0 | when no row of the table has a published value | derived |

### Sentinel and out-of-range values in `age_interval`

| Value | Rows | Meaning |
|---|---|---|
| `99` | 45,330 | the open-ended top age interval — exactly one per life table, so `[age, ∞)` |
| `-5` | 34 | upstream defect: KOR 2020 sub-national tables (Ref-IDs 3446.01-3446.02, regions 10 and 20) |
| `-105` | 3 | upstream defect: ITA 2018 sub-national tables (Ref-IDs 390.15-390.17, regions 10, 11, 70) |

A negative interval cannot define `[age, age + interval)`, so those 37 rows are
never selected. All 37 are sub-national, so no whole-country answer changes.

### Known upstream and packaging defects

| Defect | Extent | Handling |
|---|---|---|
| Life tables written with a **comma decimal separator inside a comma-delimited file**, so the row carries 25 or 26 fields where the header declares 21 | 1,290 lines in 5 tables: ITA region 200 (Ref-ID 392.09, 2020), MYS region 160 (1492.17, 2020), NZL ethnicities E020/E090/E350/E360 (3363, 3363.04-.06, 2017) | dropped, and **counted** — `build_notes.malformed_lines_dropped` records 1,290 and the build refuses to continue unless read rows plus dropped lines account for every data line. Reading them with `usecols` instead shifts every value one field left and yields e(x) of 99,775; all 5 tables are sub-national or sub-population, so no whole-country answer changes |
| `Region` written as the literal `NA` upstream, read as missing | 1,334 rows, 7 countries | treated as whole-country: the codebook has no "region unknown" code and every such row is a national table (NIU, KIR, NRU, and the single-year national tables for HUN 2018, IRN 2004, ISR 2013-17, SWE 2019) |
| Sub-population codes and `Ref-ID` written as `0.0`, `10.0`, `1.0` by a float round-trip **in this package's own packaging** | 181,953 `Region` values and 20,868 `Ref-ID` values in the old shipped CSV | gone: the build reads those columns as text. A naive `== '0'` filter on the damaged file kept 550,429 national rows where 717,457 qualify |
| Negative `AgeInt` | 37 rows, sub-national ITA and KOR | cannot define an interval, so dropped at selection |
| `e(x)` and `e(x)Orig` disagree by more than 2 years | 2,357 life tables in all, **357 of them whole-country** (15,306 national rows) | quarantined, see below |

### The selection rule

For a query `(country, year, sex, age)`, in order:

1. **Whole country, total population.** `region == residence == ethnicity ==
   socdem == '0'`. `subpopulations=True` lifts this and returns one row per
   sub-population instead.
2. **Drop `type_lt == 2`.** Type 2 is HLD's own abridgement of the type 1
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
4. **Period containment.** Keep life tables with `year1 <= year <= year2`.
   2,482 country-years in HLD are reachable only through a multi-year period
   table, so containment is required rather than optional. A year no table
   covers returns nothing; `year_tolerance` reaches to the nearest period and
   records the distance in `hld_match_status`.
5. **Narrowest period.** Of those, keep the tables with the smallest
   `year2 - year1`, so a 1980 table beats a 1976-1980 table for 1980.
6. **Age interval.** Keep the row whose interval `[age, age + age_interval)`
   contains the requested age. Many HLD tables are abridged, so age 22 is
   answered from the interval starting at 20; `hld_age` and `hld_age_interval`
   report which.
7. **Tie-break convention.** Highest `version`, then highest `ref_id_sort`,
   then latest `year1`, then lowest `type_lt`. Version is HLD's own revision
   counter, so the highest is the most revised table; Ref-ID rises as sources
   are added, so the highest is the most recently added source. The last two
   keys exist only to make the order total. About 17% of country-year cells
   reach this step with more than one candidate — median disagreement 0.38
   years, but 78 cells disagree by more than 2 — so `hld_n_candidates` reports
   the count rather than hiding it.

### What each filter costs

| Stage | Rows |
|---|---|
| read from `hld.parquet` | 2,182,429 |
| whole country, total population | 717,457 |
| drop `type_lt == 2` | 600,113 |
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

---

## SSA (US Social Security Administration)

**Source.** The Actuarial Life Table at
[`ssa.gov/oact/STATS/table4c6.html`](https://www.ssa.gov/oact/STATS/table4c6.html),
which carries one calendar year and names it — "Period Life Table, 2022, as
used in the 2025 Trustees Report". Public domain. The shipped release is the
**2022** table; the archived raw it is rebuilt from is
`data/ssa/source/ssa-2022.csv`, and `data/ssa/source/table4c6-2021.html` is a
genuine archived copy of the page for a different year, used to test the parse
against something nobody wrote to match it.

**Universe.** The Social Security area population — everyone covered by the US
Social Security programme, which is not the same as the US resident
population. **One row per single year of age, 0-119.**

**Note on fetching.** ssa.gov's edge answers many automated clients with HTTP
403 regardless of headers, so `lost_years update --source ssa` may be refused
on some networks. It says so when it is; save the page from a browser and pass
`--from-file` to run the same parse, validation and swap.

### Columns of `ssa.parquet`

| Column | Arrow type | Unit | Value set | Missing |
|---|---|---|---|---|
| `age` | `int16` | exact age, years | 0-119, complete | never |
| `male_death_prob` | `float64` | q(x): probability of dying within the year | 0-1 | never |
| `male_n_lives` | `float64` | l(x): survivors of a 100,000 birth cohort | 0-100,000 | never |
| `male_life_expectancy` | `float64` | remaining years at exact `age` | 0.50-74.74 in 2022 | never |
| `female_death_prob` | `float64` | as above, women | 0-1 | never |
| `female_n_lives` | `float64` | as above, women | 0-100,000 | never |
| `female_life_expectancy` | `float64` | as above, women | 0.50-80.18 in 2022 | never |
| `year` | `int16` | calendar year of the period table | one value per release: 2022 | never |

Age is matched to within 1 year of age; past that the lookup returns nothing
and says so in `ssa_match_status`. Calendar year is matched to the closest
table year with no default limit, because `lost_years_ssa` is explicitly a
counterfactual ("what if this person had had US mortality") — but the matched
year and its distance are always reported, and `year_tolerance` imposes a hard
limit.

---

## WHO (Global Health Observatory)

**Source.** GHO OData indicator
[`WHOSIS_000001`](https://ghoapi.azureedge.net/api/WHOSIS_000001), life
expectancy at birth. **CC BY 4.0** — attribution to the World Health
Organization is required when you redistribute figures derived from it. The
archived raw payload is `data/who/source/WHOSIS_000001.json.gz`.

**Unit of observation.** One row per population, calendar year and sex. **There
is no age dimension**: this indicator is life expectancy *at birth* only.
`lost_years_who` therefore takes no age input, returns
`who_life_expectancy_at_birth`, and raises `ValueError` if an `age` mapping is
passed. For remaining life expectancy at a given age, use `lost_years_hld`.

**Universe.** 12,936 rows, 2000-2021. **Not all rows are countries**: the
indicator also carries WHO regional, World Bank income-group and global
aggregates, and `spatial_type` says which is which. Filter on
`spatial_type == 'COUNTRY'` if you want countries only.

### Columns of `who.parquet`

| Column | Arrow type | Unit / universe | Value set | Missing |
|---|---|---|---|---|
| `country_code` | `dictionary<string>` | population | 185 ISO-3 country codes, 5 WHO region codes, 4 World Bank income groups, `GLOBAL` | never |
| `country_name` | `dictionary<string>` | display name | from `lost_years/data/who/iso_country_mapping.json` (REST Countries); falls back to the code for the 726 aggregate rows, which have no ISO name | never |
| `spatial_type` | `dictionary<string>` | what kind of population | `COUNTRY` (12,210), `REGION` (396), `WORLDBANKINCOMEGROUP` (264), `GLOBAL` (66) | never |
| `year` | `int16` | calendar year | 2000-2021 | never |
| `sex_code` | `dictionary<string>` | sex | `MLE`, `FMLE`, `BTSX` (both sexes) | never |
| `life_expectancy` | `float64` | years at birth | 36.60-87.37 | never (rows without a value are dropped) |
| `low_ci` | `float64` | lower bound of WHO's uncertainty interval | | 20 rows |
| `high_ci` | `float64` | upper bound | | 20 rows |

`ParentLocation` is deliberately **not** carried: GHO puts the WHO *region*
there, not a country name, which is how Somalia once came to be labeled
"Eastern Mediterranean".

Year is matched to the closest table year with no default limit, and the
matched year is always reported in `who_year`; `year_tolerance` imposes a hard
limit.
