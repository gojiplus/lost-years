# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Releases before 0.7.0 predate this file; see the
[commit history](https://github.com/gojiplus/lost-years/commits/master) and
[PyPI release history](https://pypi.org/project/lost-years/#history) for those.

## [Unreleased]

## [0.8.0] - 2026-08-20

### Added

- **`lost_years update [--source hld|ssa|who|all]`.** Downloads to a scratch
  directory, builds a typed Parquet table with an explicit Arrow schema,
  validates it, and **only then** swaps it into place with a same-directory
  rename. A candidate that fails any check is discarded and the table already
  installed is untouched. Validation is the declared schema field for field
  (types and nullability included), a row-count contract, and per-source value
  checks: for HLD, that the selection rule still reproduces the NCHS-published
  US male life expectancy at birth for 2018-2021 and that the national table is
  one row per life table and age; for SSA, that the table is a well-formed
  period life table; for WHO, coverage, plausible values and the sexes not
  having been exchanged.
- **`lost_years status`** reports what is installed, which upstream release it
  is, when it was fetched, and what upstream is publishing now. HLD's release
  is read out of the archive itself — the pooled file's modification time —
  and compared against lifetable.de's "What's New" page. A table whose SHA-256
  no longer matches its manifest is reported as damaged.
- **`lost_years sources`** prints where each table comes from and on what terms.
- **A provenance manifest beside every derived table**: source URL, upstream
  release identifier, fetch timestamp, row count, SHA-256 of both the table and
  the raw artifact it was built from, the full schema, and source-specific
  build notes. Nothing previously recorded where any table came from or when.
- `--from-file` builds from a local artifact, for hosts that refuse automated
  clients (ssa.gov answers many of them with HTTP 403) and for rebuilding from
  an archived copy. It is also how the test suite stays offline.


- `lost_years_hld(subpopulations=True)` returns one resolved row per
  sub-population — region, urban/rural, ethnicity, socio-demographic group —
  instead of the single national total, with the same options on the CLI
  (`--subpopulations`, `--year-tolerance`, `--no-quarantine`).
- HLD output exposes the matched period (`hld_year1`, `hld_year2`), the age
  interval (`hld_age_interval`, `99` for the open top interval), the source
  table (`hld_ref_id`, `hld_version`, `hld_type_lt`), its internal discrepancy
  (`hld_ex_discrepancy`) and the candidate count (`hld_n_candidates`).
- A data dictionary documenting the packaged tables, their known defects and
  the HLD selection rule.
- Regression tests that assert real life-expectancy values, using the
  NCHS-published US tables as an oracle. The suite previously asserted no
  life-expectancy value at all.

### Changed

- **Only the SSA table ships in the wheel**, as Parquet: 10 KB against the
  previous 52 MB of gzipped CSV and a 54 MB ZIP. HLD is not shipped because
  lifetable.de asks that users download their own copy rather than be handed
  one; WHO is not shipped because a packaged copy is stale the day WHO revises
  it. Both install with one command.
- The raw upstream artifacts moved out of the import package to
  `data/<source>/source/` and are excluded from the sdist.
- All three tables are Parquet with explicit, sized, dictionary-encoded Arrow
  schemas, asserted in the test suite.
- `[tool.preen] skip_checks = ["runtime-assets"]` is gone; the check now passes
  on its merits.
- New dependencies `pyarrow` and `platformdirs`; **`selenium` is no longer a
  runtime dependency** — a browser automation stack was being installed for a
  scraper that ran by hand, if ever.


- The usage example notebook is rewritten and re-executed against the new
  contract. The three COVID-19 notebooks are **not**: their `lost_years_who`
  cells passed an age mapping that now raises, and their HLD cells relied on
  the old silent snap to the nearest `Year1`. Re-running those analyses means
  redoing them rather than re-executing them, so they carry a warning in the
  docs instead.
- Adopted the shared `py-canon` project standard: CI, docs, release and
  Dependabot workflows now call `gojiplus/py-canon` reusable workflows.
- Documentation builds with `myst-nb` instead of `nbsphinx`, so example
  notebooks render from their committed outputs and no longer need pandoc or a
  live kernel.
- Log messages use deferred `%`-style formatting rather than f-strings.
- Timestamps in the data-maintenance scripts are timezone-aware (UTC).

### Fixed

- **1,290 upstream rows were silently discarded.** The packaging script used
  `on_bad_lines="skip"` with no count. Those lines are life tables written with
  a comma decimal separator inside a comma-delimited file, so they carry 25 or
  26 fields where the header declares 21; reading them with `usecols` instead
  shifts every value one field left and yields an `e(x)` of 99,775. They are
  still dropped — the values are not recoverable unambiguously — but they are
  now counted in the manifest, the build refuses to continue unless read rows
  plus dropped lines account for every data line, and the data dictionary names
  all five affected tables. All five are sub-national or sub-population, so no
  whole-country answer changes.
- **`Ref-ID` was damaged by the same missing `dtype=`** that damaged the
  sub-population codes: 20,868 rows reported `hld_ref_id` of `"1.0"` where HLD
  says `"1"`. The build reads it as text.
- **The WHO table mixed countries with aggregates** — WHO regions, World Bank
  income groups and a global total, 726 rows — with nothing to tell them apart.
  A `spatial_type` column now says which is which.


- **HLD returned an arbitrary life table.** The loader read 5 of the file's 21
  columns, dropping every column that identifies *which* published table a row
  belongs to, and then took `iloc[0]` from as many as 114 candidates spanning
  68.62 to 83.42 years. `lost_years_hld` now applies a documented selection
  rule — whole-country total population, HLD's redundant re-abridgements
  dropped, life tables that fail their own `e(x)` / `e(x)Orig` cross-check
  quarantined, period containment preferring the narrowest period, and a fixed
  tie-break — and reports the residual ambiguity in `hld_n_candidates`. The
  rule reproduces the NCHS-published US male life expectancy at birth for
  2018-2021 (76.2 / 76.3 / 74.2 / 73.5), including the COVID drop. See the new
  data dictionary (`docs/source/data-dictionary.md`).
- **A packaging bug hid two thirds of the national life tables.** The update
  script read the pooled file without `dtype=`, so sub-population codes went
  through float and came back as `'0.0'`; a `== '0'` test kept 550,429 rows
  where 717,457 qualify. Codes are now normalized on read, and the update
  script preserves them.
- **`US` returned Australia.** Country input was passed to `str.contains()` as
  an unanchored regular expression. Country codes are now matched exactly and
  case-insensitively.
- **A missing age returned life expectancy at birth.** `abs(x - nan)` is `nan`,
  so `closest()` fell through to the first element of the table. `closest()`
  now rejects a missing target, skips missing candidates, and takes a
  `tolerance`.
- **Years 1900 and 2500 both resolved to the 2022 SSA table.** SSA and WHO
  lookups now refuse a year more than five years from the packaged tables, and
  an age more than a year from the SSA table, reporting why in the new
  `ssa_match_status` / `who_match_status` columns.
- **WHO silently ignored age.** The packaged WHO indicator is life expectancy
  at birth and has no age dimension, but the code hardcoded `age = 1`.
  `lost_years_who` now takes no age input, returns
  `who_life_expectancy_at_birth`, and raises `ValueError` if an `age` mapping
  is passed.


- `download_file` sets a request timeout instead of blocking indefinitely.
- Local (macOS) builds no longer ship `.DS_Store` files inside the wheel.
- README documentation badge and link point at the real docs URL.

### Removed

- `lost_years.types` and its four exports (`LifeExpectancyResult`,
  `DataSourceConfig`, `ColumnConfig`, `ColumnMapping`): nothing used them.
- `lost_years/data/consolidate_data.py`, whose `consolidate_hmd_data()` wrote a
  hardcoded fake life table into the package tree. HMD is credential-gated with
  no unattended path, so this is deleted rather than repaired.
- `lost_years/data_sources.json`, which claimed SSA 2024 while shipping 2022 and
  did not mention HLD at all. `lost_years sources` reads the live registry.
- The per-source `update_*.py` maintenance scripts, `schemas.py`,
  `update_all_data.py` and the WHO scraping notebook, superseded by
  `lost_years update`.
- Dead `WHO_COLS`, `LostYearsWHOData.convert_agegroup` and its unused
  translation cache — leftovers from the age-band indicator the package does
  not use — and `hld.normalise_code`, which moved to `lost_years.sources.hld`
  where the repair now happens.

## [0.7.0]

- Packaged data refresh and Python 3.12+ support.

[Unreleased]: https://github.com/gojiplus/lost-years/commits/master
[0.8.0]: https://pypi.org/project/lost-years/0.8.0/
[0.7.0]: https://pypi.org/project/lost-years/0.7.0/
