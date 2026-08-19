# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Releases before 0.7.0 predate this file; see the
[commit history](https://github.com/gojiplus/lost-years/commits/master) and
[PyPI release history](https://pypi.org/project/lost-years/#history) for those.

## [Unreleased]

### Fixed — wrong answers

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
  where 717,457 qualify. Codes are now normalised on read, and the update
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

### Added

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

- `download_file` sets a request timeout instead of blocking indefinitely.
- Local (macOS) builds no longer ship `.DS_Store` files inside the wheel.
- README documentation badge and link point at the real docs URL.

## [0.7.0]

- Packaged data refresh and Python 3.12+ support.

[Unreleased]: https://github.com/gojiplus/lost-years/commits/master
[0.7.0]: https://pypi.org/project/lost-years/0.7.0/
