"""The contract every fetchable life-table source implements.

An update is always download to a scratch directory, build a typed table from
what arrived, check it, and only then swap it into place. The check is the
point: an upstream that truncates a file, changes a column, or ships a table
that disagrees with the published figures must not become the user's data just
because the download completed.
"""

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import requests

from ..datasets import ValidationError

logger = logging.getLogger(__name__)

# Public hosts serving multi-megabyte files; the timeout is per-read, not for
# the whole transfer.
READ_TIMEOUT = 120
USER_AGENT = "lost-years (https://github.com/gojiplus/lost-years)"


class SourceUnavailableError(RuntimeError):
    """Upstream could not be reached or refused the request."""


class Source(ABC):
    """One upstream life-table database and how to turn it into a table."""

    name: str
    title: str
    home_url: str
    download_url: str
    license: str
    filename: str
    # A release never has fewer rows than the one the package was tested
    # against, so a short table means a truncated or partial download.
    min_rows: int
    # True for the one table small enough and freely enough licensed to ship.
    ships_in_wheel: bool = False

    @abstractmethod
    def schema(self) -> pa.Schema:
        """Return the Arrow schema the derived table must conform to.

        Returns:
            The declared schema, without metadata.
        """

    @abstractmethod
    def fetch(self, workdir: Path) -> Path:
        """Download the raw upstream artifact.

        Args:
            workdir: Scratch directory to download into.

        Returns:
            Path to the downloaded artifact.
        """

    @abstractmethod
    def build(self, raw: Path, destination: Path) -> dict[str, Any]:
        """Turn a raw artifact into the derived Parquet table.

        Args:
            raw: Downloaded or locally supplied artifact.
            destination: Path to write the Parquet file to.

        Returns:
            Build notes for the manifest.
        """

    @abstractmethod
    def release_of(self, raw: Path) -> str:
        """Read the upstream release identifier out of a raw artifact.

        Args:
            raw: Downloaded or locally supplied artifact.

        Returns:
            Upstream's own identifier for the release, such as a date.
        """

    @abstractmethod
    def upstream_release(self) -> str:
        """Ask upstream what its current release is.

        Returns:
            Upstream's identifier for the release available right now.
        """

    def url_for(self, release: str) -> str:
        """Return the URL a given release is published at.

        Args:
            release: Upstream release identifier.

        Returns:
            The canonical download URL, which for most sources does not depend
            on the release.
        """
        del release
        return self.download_url

    @abstractmethod
    def check_values(self, table: pa.Table) -> None:
        """Check the values in a candidate table against known-good figures.

        Args:
            table: The candidate table.
        """

    def validate(self, path: Path) -> None:
        """Refuse a candidate table that fails schema, size or value checks.

        Args:
            path: Candidate Parquet file.

        Raises:
            ValidationError: When the table does not conform.
        """
        found = pq.read_schema(path).remove_metadata()
        expected = self.schema()
        if found != expected:
            raise ValidationError(
                f"{self.name}: schema mismatch.\nexpected:\n{expected}\ngot:\n{found}"
            )
        rows = pq.read_metadata(path).num_rows
        if rows < self.min_rows:
            raise ValidationError(
                f"{self.name}: {rows} rows, fewer than the {self.min_rows} this "
                "package was tested against. Upstream does not shrink, so this "
                "is a truncated or partial download."
            )
        self.check_values(pq.read_table(path))

    def download(self, url: str, target: Path) -> Path:
        """Stream a URL to disk, refusing a short read.

        ``Content-Length`` is the only cheap end-to-end check a plain HTTP
        download offers, so a transfer that stops early is caught here rather
        than surfacing as a corrupt archive later.

        Args:
            url: Source URL.
            target: Destination path.

        Returns:
            The destination path.

        Raises:
            SourceUnavailableError: When upstream refuses, or the transfer is short.
        """
        logger.info("Downloading %s", url)
        try:
            response = requests.get(
                url,
                timeout=READ_TIMEOUT,
                stream=True,
                headers={"User-Agent": USER_AGENT},
            )
        except requests.RequestException as exc:
            raise SourceUnavailableError(
                f"{self.name}: could not reach {url}: {exc}"
            ) from exc
        if response.status_code != 200:
            raise SourceUnavailableError(
                f"{self.name}: {url} returned HTTP {response.status_code}"
            )
        declared = response.headers.get("Content-Length")
        written = 0
        with target.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                handle.write(chunk)
                written += len(chunk)
        if declared is not None and written != int(declared):
            raise SourceUnavailableError(
                f"{self.name}: {url} announced {declared} bytes but delivered "
                f"{written}; the transfer was cut short"
            )
        logger.info("Downloaded %d bytes to %s", written, target)
        return target

    def get_text(self, url: str) -> str:
        """Fetch a small text resource.

        Args:
            url: Source URL.

        Returns:
            The response body.

        Raises:
            SourceUnavailableError: When upstream refuses or cannot be reached.
        """
        try:
            response = requests.get(
                url, timeout=READ_TIMEOUT, headers={"User-Agent": USER_AGENT}
            )
        except requests.RequestException as exc:
            raise SourceUnavailableError(
                f"{self.name}: could not reach {url}: {exc}"
            ) from exc
        if response.status_code != 200:
            raise SourceUnavailableError(
                f"{self.name}: {url} returned HTTP {response.status_code}"
            )
        return response.text
