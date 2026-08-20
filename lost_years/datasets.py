"""Where life tables live on disk, and how one is replaced without tearing.

Only the SSA table ships inside the wheel. HLD is redistributed under terms that
ask users to fetch their own copy, and the WHO table is large enough that
shipping it makes the package stale the day it is published, so both are
downloaded by ``lost_years update`` into a per-user data directory.

Every derived table is a Parquet file with an explicit Arrow schema, and every
derived table has a manifest beside it recording where it came from. A table is
only ever installed by writing it under a temporary name in its final directory
and renaming it into place, so a failed or interrupted update leaves the
previous copy exactly as it was.
"""

import hashlib
import json
import os
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from typing import Any

import platformdirs
import pyarrow as pa
import pyarrow.parquet as pq

DATA_DIR_ENV = "LOST_YEARS_DATA_DIR"

MANIFEST_SUFFIX = ".manifest.json"


class TableUnavailableError(RuntimeError):
    """A source has neither a shipped nor a downloaded table."""


class ValidationError(RuntimeError):
    """A candidate table failed a check, so it was not installed."""


def data_dir() -> Path:
    """Return the directory holding downloaded life tables.

    Returns:
        ``$LOST_YEARS_DATA_DIR`` when set, otherwise the per-user data
        directory for this platform.
    """
    override = os.environ.get(DATA_DIR_ENV)
    if override:
        return Path(override).expanduser()
    return Path(platformdirs.user_data_dir("lost_years", "gojiplus"))


def shipped_path(source: str, filename: str) -> Path:
    """Return where ``filename`` would sit inside the installed package.

    Args:
        source: Source name, e.g. ``"ssa"``.
        filename: Table file name, e.g. ``"ssa.parquet"``.

    Returns:
        Path inside the import package. It need not exist.
    """
    return Path(str(files("lost_years") / "data" / source / filename))


def installed_path(source: str, filename: str) -> Path:
    """Return where ``filename`` would sit in the user's data directory.

    Args:
        source: Source name, e.g. ``"hld"``.
        filename: Table file name, e.g. ``"hld.parquet"``.

    Returns:
        Path under :func:`data_dir`. It need not exist.
    """
    return data_dir() / source / filename


def resolve(source: str, filename: str) -> Path:
    """Find the table to read for one source.

    A downloaded table always wins over a shipped one: running
    ``lost_years update`` is how a user replaces a stale packaged table.

    Args:
        source: Source name.
        filename: Table file name.

    Returns:
        Path to an existing Parquet file.

    Raises:
        TableUnavailableError: When neither location holds the table.
    """
    downloaded = installed_path(source, filename)
    if downloaded.exists():
        return downloaded
    shipped = shipped_path(source, filename)
    if shipped.exists():
        return shipped
    raise TableUnavailableError(
        f"no {source.upper()} table on this machine. Run "
        f"`lost_years update --source {source}` to download and install one; "
        f"it will be written to {downloaded.parent}"
    )


def sha256(path: Path) -> str:
    """Return the lowercase SHA-256 digest of a file.

    Args:
        path: File to digest.

    Returns:
        64-character hexadecimal digest.
    """
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def describe_schema(schema: pa.Schema) -> list[dict[str, Any]]:
    """Render an Arrow schema as plain JSON-serialisable records.

    Args:
        schema: Schema of a derived table.

    Returns:
        One record per field, with its name, Arrow type and nullability.
    """
    return [
        {"name": field.name, "type": str(field.type), "nullable": field.nullable}
        for field in schema
    ]


def build_manifest(
    *,
    source: str,
    title: str,
    home_url: str,
    source_url: str,
    licence: str,
    upstream_release: str,
    built_from: str,
    table: Path,
    raw_sha256: str | None,
    notes: dict[str, Any],
) -> dict[str, Any]:
    """Describe a derived table and where it came from.

    Args:
        source: Source name.
        title: Human-readable name of the upstream database.
        home_url: Landing page a user should cite and read the terms on.
        source_url: URL the raw artifact was downloaded from.
        licence: Redistribution terms of the upstream data.
        upstream_release: Upstream's own identifier for this release.
        built_from: ``"download"``, or the local path the table was built from
            when the download was bypassed.
        table: The built Parquet file.
        raw_sha256: Digest of the raw artifact the table was built from, or
            None when the table was built from a local file of unknown origin.
        notes: Source-specific build facts, such as how many malformed upstream
            lines were dropped.

    Returns:
        The manifest, ready to serialise.
    """
    metadata = pq.read_metadata(table)
    return {
        "source": source,
        "title": title,
        "home_url": home_url,
        "source_url": source_url,
        "licence": licence,
        "upstream_release": upstream_release,
        "built_from": built_from,
        "fetched_at": datetime.now(tz=UTC).isoformat(timespec="seconds"),
        "filename": table.name,
        "rows": metadata.num_rows,
        "sha256": sha256(table),
        "raw_sha256": raw_sha256,
        "schema": describe_schema(pq.read_schema(table).remove_metadata()),
        "build_notes": notes,
    }


def manifest_for(table: Path) -> Path:
    """Return the manifest path beside a table.

    Args:
        table: Path to a derived table.

    Returns:
        Sibling path with the manifest suffix.
    """
    return table.with_name(table.name + MANIFEST_SUFFIX)


def read_manifest(table: Path) -> dict[str, Any] | None:
    """Read the manifest beside a table.

    Args:
        table: Path to a derived table.

    Returns:
        The manifest, or None when there is none.
    """
    path = manifest_for(table)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def install(table: Path, manifest: dict[str, Any], destination: Path) -> Path:
    """Move a validated table and its manifest into place atomically.

    Both files are written under a temporary name *in the destination
    directory*, so the rename that publishes them is a same-filesystem
    ``Path.replace``: either the old table or the new one is visible to a
    concurrent reader, never a half-written file. The table is published first,
    because it is the file readers require; a crash between the two renames
    leaves a manifest that no longer matches, which ``lost_years status``
    reports.

    Args:
        table: Validated Parquet file, anywhere on disk.
        manifest: Manifest to write beside it.
        destination: Directory to install into.

    Returns:
        The installed table path.
    """
    destination.mkdir(parents=True, exist_ok=True)
    final = destination / manifest["filename"]
    staged = destination / f".{final.name}.{os.getpid()}.tmp"
    staged.write_bytes(table.read_bytes())
    staged.replace(final)

    staged_manifest = destination / f".{final.name}{MANIFEST_SUFFIX}.{os.getpid()}.tmp"
    staged_manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    staged_manifest.replace(manifest_for(final))
    return final
