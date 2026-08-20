"""Seed the life-table cache from the repository, so no test needs the network.

The tables the lookups read are not shipped in the wheel; they are installed by
``lost_years update``. The raw upstream artifacts they are built from *are* in
the repository under ``data/<source>/source/``, so the suite builds the tables
from those with the same code path a user runs, into a cache under ``build/``
that persists between runs.

The one thing this deliberately does not do is reach upstream. A test that
wants to check the staleness report against the live site has to ask for the
network explicitly.
"""

import os
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
CACHE = REPO / "build" / "test-data"

# Source name -> the raw upstream artifact in the repository to build it from.
RAW = {
    "hld": REPO / "data" / "hld" / "source" / "hld.zip",
    "who": REPO / "data" / "who" / "source" / "WHOSIS_000001.json.gz",
}


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

    from lost_years.sources import REGISTRY
    from lost_years.update import update

    for name, raw in RAW.items():
        table = CACHE / name / REGISTRY[name].filename
        if table.exists():
            continue
        if not raw.exists():
            pytest.exit(
                f"cannot seed the {name} table: {raw} is missing from the "
                "repository, so the suite has nothing to build from"
            )
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
