"""Download raw source data into `data/raw/` reproducibly.

- The Volve DDR mirror is pinned to a commit and verified against a SHA-256, so every machine
  ingests byte-identical files.
- Sodir FactPages tables are live regulator data; each download's SHA-256 and timestamp are
  recorded in `data/raw/MANIFEST.json` so a run can be traced to the exact export it used.

Existing, verified files are never downloaded again.
"""

import hashlib
import io
import json
import tarfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Final

import httpx

from drillsage.core.errors import DependencyUnavailableError, InvalidInputError
from drillsage.core.logging import get_logger

log = get_logger(__name__)

DDR_MIRROR_REPO: Final = "bysarmad/Well-Data-Management-and-Visualization"
DDR_MIRROR_COMMIT: Final = "f9202a244b2e864a77cab2140cbee899fd6be5b4"
DDR_MIRROR_SHA256: Final = "9d8fccaf4e0ea43b0bfe3564a8f65dd51e4f6c4e0e46562083146ce85060da3e"
DDR_MIRROR_DIR: Final = "volve_ddr_mirror"
_DDR_MEMBERS: Final = ("Reports/", "Data/volve_wells.csv")

SODIR_DIR: Final = "sodir"
SODIR_TABLES: Final = (
    "wellbore_exploration_all",
    "wellbore_development_all",
    "strat_litho_wellbore",
)
_SODIR_URL: Final = (
    "https://factpages.sodir.no/public?/Factpages/external/tableview/{table}"
    "&rs:Command=Render&rc:Toolbar=false&rc:Parameters=f&IpAddress=not_used"
    "&CultureCode=en&rs:Format=CSV&Top100=false"
)
_MAX_DOWNLOAD_BYTES: Final = 64 * 1024 * 1024
_TIMEOUT: Final = httpx.Timeout(30.0, read=120.0)


class ChecksumMismatchError(InvalidInputError):
    slug = "checksum-mismatch"


class UnsafeArchiveError(InvalidInputError):
    slug = "unsafe-archive"


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    source: str
    url: str
    sha256: str
    fetched_at: str
    pinned: bool


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _download(client: httpx.Client, url: str) -> bytes:
    try:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            buffer = io.BytesIO()
            for chunk in response.iter_bytes():
                buffer.write(chunk)
                if buffer.tell() > _MAX_DOWNLOAD_BYTES:
                    raise InvalidInputError(f"download from {url} exceeds size limit")
    except httpx.HTTPError as exc:
        raise DependencyUnavailableError(f"download failed: {url}: {exc}") from exc
    return buffer.getvalue()


def _safe_member_path(name: str) -> PurePosixPath | None:
    """Path inside the archive's top folder, or None when it is not a file we want.

    Rejects absolute paths and `..` components (zip-slip).
    """
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise UnsafeArchiveError(f"archive member escapes target directory: {name!r}")
    rest = path.parts[1:]
    if not rest:
        return None
    inner = PurePosixPath(*rest)
    text = inner.as_posix()
    wanted = any(text.startswith(m) if m.endswith("/") else text == m for m in _DDR_MEMBERS)
    return inner if wanted else None


def extract_ddr_archive(archive: bytes, target: Path) -> int:
    """Extract the wanted members of the mirror tarball into `target`; returns files written."""
    written = 0
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        for member in tar.getmembers():
            inner = _safe_member_path(member.name)
            if inner is None or member.isdir():
                continue
            if not member.isfile():
                raise UnsafeArchiveError(f"refusing non-regular archive member {member.name!r}")
            source = tar.extractfile(member)
            if source is None:
                continue
            destination = target / inner
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(source.read())
            written += 1
    return written


def _load_manifest(path: Path) -> dict[str, ManifestEntry]:
    if not path.exists():
        return {}
    raw: dict[str, dict[str, str | bool]] = json.loads(path.read_text(encoding="utf-8"))
    return {
        key: ManifestEntry(
            source=str(v["source"]),
            url=str(v["url"]),
            sha256=str(v["sha256"]),
            fetched_at=str(v["fetched_at"]),
            pinned=bool(v["pinned"]),
        )
        for key, v in raw.items()
    }


def _save_manifest(path: Path, manifest: dict[str, ManifestEntry]) -> None:
    payload = {key: asdict(entry) for key, entry in sorted(manifest.items())}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def fetch_all(
    raw_dir: Path, *, refresh_sodir: bool = False, transport: httpx.BaseTransport | None = None
) -> dict[str, ManifestEntry]:
    """Ensure every raw source exists under `raw_dir`; returns the manifest.

    `transport` replaces the network in tests.
    """
    raw_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = raw_dir / "MANIFEST.json"
    manifest = _load_manifest(manifest_path)
    now = datetime.now(UTC).isoformat(timespec="seconds")

    with httpx.Client(timeout=_TIMEOUT, follow_redirects=True, transport=transport) as client:
        ddr_dir = raw_dir / DDR_MIRROR_DIR
        entry = manifest.get(DDR_MIRROR_DIR)
        if entry is None or entry.sha256 != DDR_MIRROR_SHA256 or not (ddr_dir / "Reports").is_dir():
            url = f"https://codeload.github.com/{DDR_MIRROR_REPO}/tar.gz/{DDR_MIRROR_COMMIT}"
            archive = _download(client, url)
            digest = sha256_bytes(archive)
            if digest != DDR_MIRROR_SHA256:
                raise ChecksumMismatchError(
                    f"DDR mirror checksum {digest} does not match pinned {DDR_MIRROR_SHA256}"
                )
            count = extract_ddr_archive(archive, ddr_dir)
            manifest[DDR_MIRROR_DIR] = ManifestEntry(DDR_MIRROR_REPO, url, digest, now, pinned=True)
            log.info("fetched_ddr_mirror", files=count, commit=DDR_MIRROR_COMMIT)
        else:
            log.info("ddr_mirror_present", path=str(ddr_dir))

        sodir_dir = raw_dir / SODIR_DIR
        sodir_dir.mkdir(exist_ok=True)
        for table in SODIR_TABLES:
            key = f"{SODIR_DIR}/{table}"
            path = sodir_dir / f"{table}.csv"
            if path.exists() and key in manifest and not refresh_sodir:
                continue
            url = _SODIR_URL.format(table=table)
            data = _download(client, url)
            if b"," not in data[:200]:
                raise InvalidInputError(f"Sodir {table}: response is not CSV")
            path.write_bytes(data)
            manifest[key] = ManifestEntry(
                "Sodir FactPages", url, sha256_bytes(data), now, pinned=False
            )
            log.info("fetched_sodir_table", table=table, bytes=len(data))

    _save_manifest(manifest_path, manifest)
    return manifest
