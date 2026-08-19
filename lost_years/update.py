"""Install a life table: download, build, validate, then swap it into place.

Nothing is ever written over a working table until a candidate has passed every
check, so an upstream that truncates a file, renames a column, or ships a table
that no longer reproduces the published figures leaves the user with what they
already had rather than with quietly wrong numbers.
"""

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .datasets import (
    build_manifest,
    data_dir,
    installed_path,
    read_manifest,
    resolve,
    sha256,
    shipped_path,
)
from .datasets import install as install_table
from .sources import Source, SourceUnavailableError, get_source

logger = logging.getLogger(__name__)

WORK_DIRNAME = ".work"

STATE_CURRENT = "current"
STATE_STALE = "stale"
STATE_UNKNOWN = "unknown"
STATE_MISSING = "missing"
STATE_DAMAGED = "damaged"


@dataclass(frozen=True)
class UpdateResult:
    """What one ``lost_years update`` of a single source did."""

    source: str
    path: Path
    manifest: dict[str, Any]
    replaced: bool


@dataclass(frozen=True)
class SourceStatus:
    """What is installed for one source, and whether upstream has moved on."""

    source: str
    kind: str
    path: Path | None
    installed_release: str | None
    fetched_at: str | None
    rows: int | None
    upstream_release: str | None
    state: str
    note: str


def update(
    name: str,
    *,
    from_file: Path | None = None,
    destination: Path | None = None,
) -> UpdateResult:
    """Fetch, build, validate and install one source's table.

    Args:
        name: Source name.
        from_file: Build from this local artifact instead of downloading. The
            escape hatch for hosts that refuse automated clients, and the way
            to rebuild from an archived copy.
        destination: Directory to install into. Defaults to the per-user data
            directory; the maintainer scripts point it at the package tree to
            regenerate the one table that ships.

    Returns:
        Where the table landed and what its manifest says.
    """
    source = get_source(name)
    target = destination or (data_dir() / source.name)
    workroot = data_dir() / WORK_DIRNAME
    workroot.mkdir(parents=True, exist_ok=True)
    previous = target / source.filename

    with tempfile.TemporaryDirectory(dir=workroot, prefix=f"{name}-") as scratch:
        scratch_dir = Path(scratch)
        raw = Path(from_file) if from_file else source.fetch(scratch_dir)
        release = source.release_of(raw)
        logger.info("%s: upstream release %s", name, release)

        candidate = scratch_dir / source.filename
        notes = source.build(raw, candidate)
        source.validate(candidate)
        logger.info("%s: candidate table passed validation", name)

        manifest = build_manifest(
            source=source.name,
            title=source.title,
            home_url=source.home_url,
            source_url=source.url_for(release),
            licence=source.licence,
            upstream_release=release,
            built_from=str(from_file) if from_file else "download",
            table=candidate,
            raw_sha256=sha256(raw),
            notes=notes,
        )
        replaced = previous.exists()
        installed = install_table(candidate, manifest, target)

    logger.info("%s: installed %s", name, installed)
    return UpdateResult(
        source=name, path=installed, manifest=manifest, replaced=replaced
    )


def _installed_table(source: Source) -> tuple[str, Path | None]:
    """Find which copy of a source's table would be read.

    Args:
        source: The source.

    Returns:
        How the table got there, and its path, or ``(STATE_MISSING, None)``.
    """
    downloaded = installed_path(source.name, source.filename)
    if downloaded.exists():
        return "downloaded", downloaded
    shipped = shipped_path(source.name, source.filename)
    if shipped.exists():
        return "shipped", shipped
    return STATE_MISSING, None


def status(name: str, *, check_upstream: bool = True) -> SourceStatus:
    """Report what is installed for one source and whether it is current.

    Args:
        name: Source name.
        check_upstream: Ask upstream what it is publishing now. Set False for
            an offline report of what is installed.

    Returns:
        The report.
    """
    source = get_source(name)
    kind, path = _installed_table(source)
    manifest = read_manifest(path) if path else None
    installed_release = manifest.get("upstream_release") if manifest else None
    rows = manifest.get("rows") if manifest else None
    fetched_at = manifest.get("fetched_at") if manifest else None

    if path is None:
        return SourceStatus(
            source=name,
            kind=kind,
            path=None,
            installed_release=None,
            fetched_at=None,
            rows=None,
            upstream_release=None,
            state=STATE_MISSING,
            note=f"run `lost_years update --source {name}`",
        )

    if manifest and sha256(path) != manifest.get("sha256"):
        return SourceStatus(
            source=name,
            kind=kind,
            path=path,
            installed_release=installed_release,
            fetched_at=fetched_at,
            rows=rows,
            upstream_release=None,
            state=STATE_DAMAGED,
            note=(
                "the table does not match its manifest; re-run "
                f"`lost_years update --source {name}`"
            ),
        )

    upstream = None
    note = ""
    state = STATE_UNKNOWN
    if check_upstream:
        try:
            upstream = source.upstream_release()
        except (SourceUnavailableError, ValueError) as exc:
            note = str(exc)
        else:
            # Release identifiers are ISO dates (HLD) or years (SSA, WHO), so
            # they order lexically. Ahead of what upstream announces is not
            # stale: the HLD archive's own timestamp routinely runs a couple of
            # weeks ahead of the newest entry on its "What's New" page.
            if installed_release is None:
                note = "no manifest, so the installed release is unknown"
            elif str(upstream) <= str(installed_release):
                state = STATE_CURRENT
                if str(upstream) < str(installed_release):
                    note = f"ahead of the {upstream} release upstream announces"
            else:
                state = STATE_STALE
                note = (
                    f"upstream has moved to {upstream}; run "
                    f"`lost_years update --source {name}`"
                )
    else:
        note = "upstream not checked"

    return SourceStatus(
        source=name,
        kind=kind,
        path=path,
        installed_release=installed_release,
        fetched_at=fetched_at,
        rows=rows,
        upstream_release=upstream,
        state=state,
        note=note,
    )


def table_path(name: str) -> Path:
    """Return the table a lookup for this source would read.

    Args:
        name: Source name.

    Returns:
        Path to the Parquet file.
    """
    source = get_source(name)
    return resolve(source.name, source.filename)
