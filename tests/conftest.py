"""Seed the life-table cache so no test needs the network more than once.

The tables the lookups read are not shipped in the wheel; they are installed by
``lost_years update``. The suite builds them with the same code path a user
runs, into a cache under ``build/`` that persists between runs.

WHO's raw payload is CC BY 4.0 and 600 KB, so it is in the repository. HLD's is
not: lifetable.de asks that users download their own copy rather than be
handed one, and this suite is a user like any other. It reads the maintainer's
own copy at ``data/hld/source/hld.zip`` when there is one (gitignored), and
otherwise downloads one into the cache -- about 56 MB, two to three minutes on
a GitHub runner. That is the one network access the suite makes on its own.
Anything else that wants upstream has to ask for it explicitly.
"""

import os
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
CACHE = REPO / "build" / "test-data"

LOCAL_HLD_ZIP = REPO / "data" / "hld" / "source" / "hld.zip"
CACHED_HLD_ZIP = CACHE / "raw" / "hld.zip"

# Source name -> the raw upstream artifact to build it from. The HLD path is
# fixed at import time but may not exist until the session fixture has run.
RAW = {
    "hld": LOCAL_HLD_ZIP if LOCAL_HLD_ZIP.exists() else CACHED_HLD_ZIP,
    "who": REPO / "data" / "who" / "source" / "WHOSIS_000001.json.gz",
}


def fetch_hld_zip() -> Path:
    """Make sure the raw HLD archive is on disk, downloading it if it is not.

    The download lands under a staging name and is renamed into place, so a
    run killed mid-transfer leaves nothing a later run could mistake for a
    complete archive.

    Returns:
        Path to the archive the suite will build from.
    """
    if RAW["hld"].exists():
        return RAW["hld"]
    from lost_years.sources.hld import HLD

    staging = CACHED_HLD_ZIP.parent / ".download"
    staging.mkdir(parents=True, exist_ok=True)
    downloaded = HLD().fetch(staging)
    downloaded.replace(CACHED_HLD_ZIP)
    return CACHED_HLD_ZIP


def clear_table_caches() -> None:
    """Drop every in-process copy of a life table.

    The lookups cache the table they read, so a test that points the package at
    a different data directory has to clear them or it will keep answering from
    the previous one.
    """
    from lost_years import hld, ssa, who

    hld.read_hld.cache_clear()
    hld.load_hld_table.cache_clear()
    ssa.LostYearsSSAData._LostYearsSSAData__df = None
    who.LostYearsWHOData._LostYearsWHOData__df = None


@pytest.fixture(scope="session", autouse=True)
def life_tables() -> None:
    """Point the package at the test cache and fill it once per session."""
    os.environ["LOST_YEARS_DATA_DIR"] = str(CACHE)
    CACHE.mkdir(parents=True, exist_ok=True)

    from lost_years.datasets import read_manifest, sha256
    from lost_years.sources import REGISTRY
    from lost_years.update import update

    for name, raw in RAW.items():
        if name == "hld":
            raw = fetch_hld_zip()
        elif not raw.exists():
            pytest.exit(
                f"cannot seed the {name} table: {raw} is missing from the "
                "repository, so the suite has nothing to build from"
            )
        table = CACHE / name / REGISTRY[name].filename
        # A cached table built from some other copy of the archive -- the
        # maintainer swapped in a newer release, say -- would make every
        # provenance assertion lie, so the manifest's digest is the cache key.
        manifest = read_manifest(table) if table.exists() else None
        if manifest and manifest.get("raw_sha256") == sha256(raw):
            continue
        update(name, from_file=raw, destination=CACHE / name)


@pytest.fixture
def scratch_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Give one test an empty data directory of its own.

    Args:
        tmp_path: Per-test temporary directory.
        monkeypatch: Environment patcher.

    Yields:
        The empty data directory.
    """
    monkeypatch.setenv("LOST_YEARS_DATA_DIR", str(tmp_path / "data"))
    clear_table_caches()
    yield tmp_path / "data"
    clear_table_caches()


@pytest.fixture
def seeded_cache(scratch_cache: Path) -> Path:
    """Give one test its own data directory already holding the HLD table.

    Args:
        scratch_cache: The empty data directory.

    Returns:
        The data directory, with ``hld/`` populated.
    """
    shutil.copytree(CACHE / "hld", scratch_cache / "hld")
    return scratch_cache
