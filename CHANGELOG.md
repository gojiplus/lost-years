# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Releases before 0.7.0 predate this file; see the
[commit history](https://github.com/gojiplus/lost-years/commits/master) and
[PyPI release history](https://pypi.org/project/lost-years/#history) for those.

## [Unreleased]

### Changed

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
