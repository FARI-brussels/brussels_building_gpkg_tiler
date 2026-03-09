from __future__ import annotations

import json
import zipfile
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Polygon

from src.urbis_feed import run_urbis_feed_pipeline, select_latest_download


def _write_sample_gpkg(gpkg_path: Path) -> None:
    wall = Polygon(
        [
            (0.0, 0.0, 0.0),
            (0.0, 0.0, 3.0),
            (4.0, 0.0, 3.0),
            (4.0, 0.0, 0.0),
            (0.0, 0.0, 0.0),
        ]
    )
    roof = Polygon(
        [
            (0.0, 0.0, 3.0),
            (4.0, 0.0, 3.0),
            (4.0, 4.0, 3.0),
            (0.0, 4.0, 3.0),
            (0.0, 0.0, 3.0),
        ]
    )
    gdf = gpd.GeoDataFrame(
        {
            "building_id": ["bldg-1", "bldg-1"],
            "surface_type": ["WallSurface", "RoofSurface"],
            "geometry": [wall, roof],
        },
        crs="EPSG:31370",
    )
    gdf.to_file(gpkg_path, layer="surfaces", driver="GPKG")


def test_select_latest_download_prefers_newest_matching_link(tmp_path: Path) -> None:
    feed_path = tmp_path / "feed.xml"
    feed_path.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <link rel="section" href="https://example.test/older.zip" type="application/geopackage+sqlite3" time="2026-03-05T00:00:00Z" sectionID="04000" title="Région de Bruxelles-Capitale"/>
  <link rel="section" href="https://example.test/latest.zip" type="application/geopackage+sqlite3" time="2026-03-07T00:00:00Z" sectionID="04000" title="Région de Bruxelles-Capitale"/>
  <link rel="section" href="https://example.test/other.zip" type="application/geopackage+sqlite3" time="2026-03-08T00:00:00Z" sectionID="01000" title="Brussels-City"/>
</feed>
""",
        encoding="utf-8",
    )

    selected = select_latest_download(str(feed_path))

    assert selected.href == "https://example.test/latest.zip"
    assert selected.section_id == "04000"


def test_run_urbis_feed_pipeline_downloads_extracts_and_exports(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir()
    gpkg_path = dataset_dir / "urbis_buildings.gpkg"
    _write_sample_gpkg(gpkg_path)

    archive_path = tmp_path / "UrbISBuildings3D_31370_GPKG_04000_20260307.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.write(gpkg_path, arcname="nested/urbis_buildings.gpkg")

    feed_path = tmp_path / "feed.xml"
    feed_path.write_text(
        f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <link rel="section" href="{archive_path.resolve().as_uri()}" type="application/geopackage+sqlite3" time="2026-03-07T00:00:00Z" sectionID="04000" title="Région de Bruxelles-Capitale"/>
</feed>
""",
        encoding="utf-8",
    )

    result = run_urbis_feed_pipeline(
        str(feed_path),
        tmp_path / "output",
        layer="surfaces",
        building_id_field="building_id",
        class_field="surface_type",
    )

    assert result.archive_path.exists()
    assert result.gpkg_path.exists()
    assert result.with_elevation_tileset.exists()
    assert result.no_elevation_tileset.exists()

    with_elevation = json.loads(result.with_elevation_tileset.read_text(encoding="utf-8"))
    no_elevation = json.loads(result.no_elevation_tileset.read_text(encoding="utf-8"))
    assert with_elevation["asset"]["version"] == "1.1"
    assert no_elevation["asset"]["version"] == "1.1"
