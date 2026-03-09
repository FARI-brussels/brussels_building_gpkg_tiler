from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen
import shutil
import zipfile
import xml.etree.ElementTree as ET

from .tiler import export_gpkg_to_3d_tiles


@dataclass(slots=True, frozen=True)
class AtomDownload:
    href: str
    timestamp: datetime
    section_id: str | None
    title: str | None


@dataclass(slots=True, frozen=True)
class UrbisFeedResult:
    archive_path: Path
    gpkg_path: Path
    with_elevation_tileset: Path
    no_elevation_tileset: Path


def _read_text(source: str) -> str:
    path = Path(source).expanduser()
    if path.exists():
        return path.read_text(encoding="utf-8")
    with urlopen(source) as response:
        return response.read().decode("utf-8")


def _copy_href_to_path(href: str, destination: Path) -> Path:
    parsed = urlparse(href)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if parsed.scheme == "file":
        source_path = Path(parsed.path)
        shutil.copy2(source_path, destination)
        return destination
    if parsed.scheme in {"http", "https"}:
        with urlopen(href) as response, destination.open("wb") as handle:
            shutil.copyfileobj(response, handle)
        return destination

    source_path = Path(href).expanduser()
    shutil.copy2(source_path, destination)
    return destination


def _parse_timestamp(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def select_latest_download(feed_source: str, *, preferred_section_id: str = "04000") -> AtomDownload:
    root = ET.fromstring(_read_text(feed_source))
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    candidates: list[AtomDownload] = []
    for link in root.findall("atom:link", ns):
        href = link.attrib.get("href")
        timestamp = link.attrib.get("time")
        if not href or not timestamp:
            continue
        if link.attrib.get("rel") != "section":
            continue
        content_type = (link.attrib.get("type") or "").lower()
        if "geopackage" not in content_type and not href.lower().endswith(".zip"):
            continue
        candidates.append(
            AtomDownload(
                href=href,
                timestamp=_parse_timestamp(timestamp),
                section_id=link.attrib.get("sectionID"),
                title=link.attrib.get("title"),
            )
        )

    if not candidates:
        raise ValueError("No GeoPackage download links were found in the Atom feed.")

    preferred = [candidate for candidate in candidates if candidate.section_id == preferred_section_id]
    pool = preferred or candidates
    return max(pool, key=lambda candidate: candidate.timestamp)


def _extract_first_gpkg(archive_path: Path, destination_dir: Path) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        gpkg_members = [member for member in archive.namelist() if member.lower().endswith(".gpkg")]
        if not gpkg_members:
            raise ValueError(f"No .gpkg file found in archive {archive_path}")
        member = gpkg_members[0]
        extracted_path = Path(archive.extract(member, path=destination_dir))
    return extracted_path


def run_urbis_feed_pipeline(
    feed_source: str,
    output_dir: Path,
    *,
    layer: str | None = None,
    building_id_field: str | None = None,
    class_field: str | None = None,
    default_class: str = "default",
    tile_size: float = 250.0,
    root_geometric_error: float | None = None,
    with_metadata: bool = False,
    overwrite: bool = False,
) -> UrbisFeedResult:
    output_dir = output_dir.expanduser().resolve()
    source_dir = output_dir / "source"
    selected = select_latest_download(feed_source)
    archive_name = Path(urlparse(selected.href).path).name or "urbis_download.zip"
    archive_path = _copy_href_to_path(selected.href, source_dir / archive_name)
    gpkg_path = _extract_first_gpkg(archive_path, source_dir / "extracted")

    with_elevation_tileset = export_gpkg_to_3d_tiles(
        gpkg_path,
        output_dir / "with_elevation",
        layer=layer,
        building_id_field=building_id_field,
        class_field=class_field,
        default_class=default_class,
        tile_size=tile_size,
        root_geometric_error=root_geometric_error,
        no_elevation=False,
        with_metadata=with_metadata,
        overwrite=overwrite,
    )
    no_elevation_tileset = export_gpkg_to_3d_tiles(
        gpkg_path,
        output_dir / "no_elevation",
        layer=layer,
        building_id_field=building_id_field,
        class_field=class_field,
        default_class=default_class,
        tile_size=tile_size,
        root_geometric_error=root_geometric_error,
        no_elevation=True,
        with_metadata=with_metadata,
        overwrite=overwrite,
    )

    return UrbisFeedResult(
        archive_path=archive_path,
        gpkg_path=gpkg_path,
        with_elevation_tileset=with_elevation_tileset,
        no_elevation_tileset=no_elevation_tileset,
    )
