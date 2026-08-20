"""The ``lost_years`` command: install life tables and report on them."""

import argparse
import logging
import sys
from pathlib import Path

from .datasets import DATA_DIR_ENV, ValidationError, data_dir
from .sources import REGISTRY, SourceUnavailableError
from .update import status, update

logger = logging.getLogger(__name__)

SOURCE_CHOICES = [*sorted(REGISTRY), "all"]


def _selected(name: str) -> list[str]:
    """Expand the ``--source`` argument into source names.

    Args:
        name: A source name or ``"all"``.

    Returns:
        The source names to act on.
    """
    return sorted(REGISTRY) if name == "all" else [name]


def _describe(source: str) -> str:
    """Render one source's registry entry for ``lost_years sources``.

    Args:
        source: Source name.

    Returns:
        A block of text describing the source.
    """
    entry = REGISTRY[source]
    ships = "ships in the wheel" if entry.ships_in_wheel else "downloaded on request"
    return (
        f"{entry.name}: {entry.title}\n"
        f"  home     {entry.home_url}\n"
        f"  download {entry.download_url}\n"
        f"  license  {entry.license}\n"
        f"  table    {entry.filename} ({ships})"
    )


def _run_update(args: argparse.Namespace) -> int:
    """Install the selected sources.

    Args:
        args: Parsed arguments.

    Returns:
        0 when every selected source installed, 1 otherwise.
    """
    failures = 0
    for name in _selected(args.source):
        try:
            result = update(
                name,
                from_file=Path(args.from_file) if args.from_file else None,
                destination=Path(args.output) if args.output else None,
            )
        except (SourceUnavailableError, ValidationError) as exc:
            failures += 1
            print(f"{name}: NOT updated -- {exc}")
            continue
        verb = "replaced" if result.replaced else "installed"
        print(
            f"{name}: {verb} {result.path} "
            f"({result.manifest['rows']:,} rows, upstream release "
            f"{result.manifest['upstream_release']})"
        )
    return 1 if failures else 0


def _run_status(args: argparse.Namespace) -> int:
    """Report what is installed and whether upstream has moved.

    Args:
        args: Parsed arguments.

    Returns:
        0 always; staleness is reported, not treated as an error.
    """
    print(f"data directory: {data_dir()}  (override with ${DATA_DIR_ENV})")
    header = f"{'source':<7} {'state':<9} {'installed':<12} {'upstream':<12} rows"
    print(header)
    print("-" * len(header))
    for name in _selected(args.source):
        report = status(name, check_upstream=not args.offline)
        rows = f"{report.rows:,}" if report.rows else "-"
        print(
            f"{name:<7} {report.state:<9} "
            f"{report.installed_release or '-':<12} "
            f"{report.upstream_release or '-':<12} {rows}"
        )
        if report.path:
            print(f"        {report.kind}: {report.path}")
        if report.fetched_at:
            print(f"        fetched {report.fetched_at}")
        if report.note:
            print(f"        {report.note}")
    return 0


def _run_sources(args: argparse.Namespace) -> int:
    """Print the source registry.

    Args:
        args: Parsed arguments.

    Returns:
        0.
    """
    for name in _selected(args.source):
        print(_describe(name))
        print()
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the ``lost_years`` argument parser.

    Returns:
        The parser.
    """
    parser = argparse.ArgumentParser(
        prog="lost_years",
        description="Install and inspect the life tables lost_years reads.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    updater = subparsers.add_parser(
        "update",
        help="download, validate and install a life table",
        description=(
            "Downloads to a scratch directory, builds a typed table, checks it "
            "against the declared schema, a row-count contract and the "
            "published figures, and only then swaps it into place."
        ),
    )
    updater.add_argument(
        "--source", default="all", choices=SOURCE_CHOICES, help="which source to update"
    )
    updater.add_argument(
        "--from-file",
        default=None,
        help=(
            "build from this local artifact instead of downloading, for hosts "
            "that refuse automated clients"
        ),
    )
    updater.add_argument(
        "--output",
        default=None,
        help="install into this directory instead of the per-user data directory",
    )
    updater.set_defaults(handler=_run_update)

    reporter = subparsers.add_parser(
        "status",
        help="report the installed release and whether upstream has moved",
    )
    reporter.add_argument("--source", default="all", choices=SOURCE_CHOICES)
    reporter.add_argument(
        "--offline",
        action="store_true",
        help="report what is installed without contacting upstream",
    )
    reporter.set_defaults(handler=_run_status)

    lister = subparsers.add_parser(
        "sources", help="print where each life table comes from and on what terms"
    )
    lister.add_argument("--source", default="all", choices=SOURCE_CHOICES)
    lister.set_defaults(handler=_run_sources)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the ``lost_years`` command line interface.

    Args:
        argv: Command line arguments, defaulting to the process arguments.

    Returns:
        Process exit status.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    return int(args.handler(args))


if __name__ == "__main__":
    sys.exit(main())
