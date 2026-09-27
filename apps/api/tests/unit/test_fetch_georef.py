import io
import json
import tarfile
from pathlib import Path

import httpx
import pytest

from drillsage.core.errors import DependencyUnavailableError, InvalidInputError
from drillsage.ingest import fetch
from drillsage.ingest.fetch import (
    ChecksumMismatchError,
    UnsafeArchiveError,
    extract_ddr_archive,
    fetch_all,
    sha256_bytes,
)
from drillsage.ingest.georef import to_wgs84, utm_epsg_for, utm_to_wgs84


def _tarball(members: dict[str, bytes], *, symlink: str | None = None) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        if symlink is not None:
            link = tarfile.TarInfo(symlink)
            link.type = tarfile.SYMTYPE
            link.linkname = "/etc/passwd"
            tar.addfile(link)
    return buffer.getvalue()


def test_extract_keeps_only_reports_and_well_list(tmp_path: Path) -> None:
    archive = _tarball(
        {
            "repo-sha/Reports/a.xml": b"<a/>",
            "repo-sha/Data/volve_wells.csv": b"x",
            "repo-sha/app.py": b"print()",
            "repo-sha/README.md": b"#",
        }
    )
    assert extract_ddr_archive(archive, tmp_path) == 2
    assert (tmp_path / "Reports" / "a.xml").read_bytes() == b"<a/>"
    assert not (tmp_path / "app.py").exists()


@pytest.mark.parametrize("name", ["repo/../../evil.xml", "/abs/Reports/x.xml", "../Reports/x.xml"])
def test_extract_rejects_path_traversal(tmp_path: Path, name: str) -> None:
    with pytest.raises(UnsafeArchiveError):
        extract_ddr_archive(_tarball({name: b"x"}), tmp_path)


def test_extract_rejects_links(tmp_path: Path) -> None:
    with pytest.raises(UnsafeArchiveError, match="non-regular"):
        extract_ddr_archive(_tarball({}, symlink="repo/Reports/link.xml"), tmp_path)


def _transport(archive: bytes, csv: bytes = b"a,b\n1,2\n") -> httpx.MockTransport:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if "codeload.github.com" in str(request.url):
            return httpx.Response(200, content=archive)
        return httpx.Response(200, content=csv)

    transport = httpx.MockTransport(handler)
    transport.calls = calls  # type: ignore[attr-defined]
    return transport


def test_fetch_all_verifies_checksum_and_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = _tarball({"r/Reports/x.xml": b"<x/>"})
    monkeypatch.setattr(fetch, "DDR_MIRROR_SHA256", sha256_bytes(archive))
    transport = _transport(archive)

    manifest = fetch_all(tmp_path, transport=transport)
    assert (tmp_path / "volve_ddr_mirror" / "Reports" / "x.xml").exists()
    assert set(manifest) == {"volve_ddr_mirror", *(f"sodir/{t}" for t in fetch.SODIR_TABLES)}
    assert manifest["volve_ddr_mirror"].pinned
    saved = json.loads((tmp_path / "MANIFEST.json").read_text())
    assert saved["volve_ddr_mirror"]["sha256"] == sha256_bytes(archive)
    first_calls = len(transport.calls)  # type: ignore[attr-defined]

    fetch_all(tmp_path, transport=transport)
    assert len(transport.calls) == first_calls  # type: ignore[attr-defined]
    fetch_all(tmp_path, transport=transport, refresh_sodir=True)
    assert len(transport.calls) == first_calls + len(fetch.SODIR_TABLES)  # type: ignore[attr-defined]


def test_fetch_all_rejects_tampered_archive(tmp_path: Path) -> None:
    with pytest.raises(ChecksumMismatchError):
        fetch_all(tmp_path, transport=_transport(b"not the pinned archive"))


def test_fetch_all_rejects_non_csv_sodir_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = _tarball({"r/Reports/x.xml": b"<x/>"})
    monkeypatch.setattr(fetch, "DDR_MIRROR_SHA256", sha256_bytes(archive))
    with pytest.raises(InvalidInputError, match="not CSV"):
        fetch_all(tmp_path, transport=_transport(archive, csv=b"<html>maintenance</html>"))


def test_fetch_all_maps_network_errors(tmp_path: Path) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    with pytest.raises(DependencyUnavailableError, match="download failed"):
        fetch_all(tmp_path, transport=httpx.MockTransport(fail))


def test_ed50_to_wgs84_shift_is_realistic_for_the_north_sea() -> None:
    # ED50 → WGS84 in the North Sea moves points roughly 100 m south-west.
    location = to_wgs84(58.441642, 1.887419, "ED50")
    assert location.utm_epsg == 32631
    assert -0.0015 < location.lat_deg - 58.441642 < 0
    assert -0.003 < location.lon_deg - 1.887419 < 0
    lat, lon = utm_to_wgs84(location.easting_m, location.northing_m, location.utm_epsg)
    assert lat == pytest.approx(location.lat_deg, abs=1e-9)
    assert lon == pytest.approx(location.lon_deg, abs=1e-9)
    with pytest.raises(ValueError, match="unsupported geodetic datum"):
        to_wgs84(0, 0, "NAD27")


def test_utm_zone_selection() -> None:
    assert utm_epsg_for(1.9, 58.4) == 32631
    assert utm_epsg_for(94.9, 27.5) == 32646  # Upper Assam
    assert utm_epsg_for(-70.0, -33.0) == 32719
