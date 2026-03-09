from __future__ import annotations

import contextlib
import json
import zipfile
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import geopandas as gpd
from shapely.geometry import Polygon

from src.config import PipelineConfig
from src.pipeline.runner import run_pipeline


def test_pipeline_config_and_runner(tmp_path: Path) -> None:
    gpkg_path = tmp_path / "surfaces.gpkg"
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

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
inputs:
  gpkg_path: surfaces.gpkg
  layer: surfaces
  building_id_field: building_id
  class_field: surface_type
tiling:
  tile_size: 250.0
  overwrite: true
artifacts:
  output_dir: tiles_output
""".strip(),
        encoding="utf-8",
    )

    cfg = PipelineConfig.from_yaml(config_path)
    cfg.inputs.gpkg_path = config_path.parent / cfg.inputs.gpkg_path
    cfg.artifacts.output_dir = config_path.parent / cfg.artifacts.output_dir

    metrics = run_pipeline(cfg)

    assert metrics.tile_count == 1
    tileset = json.loads(metrics.tileset_path.read_text(encoding="utf-8"))
    assert tileset["asset"]["version"] == "1.1"
    assert metrics.output_dir == config_path.parent / "tiles_output"


def test_pipeline_config_and_runner_accepts_zip_url_input(tmp_path: Path) -> None:
    gpkg_path = tmp_path / "surfaces.gpkg"
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

    archive_path = tmp_path / "surfaces.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.write(gpkg_path, arcname="nested/surfaces.gpkg")

    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

    handler = partial(QuietHandler, directory=str(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        archive_url = f"http://127.0.0.1:{server.server_port}/{archive_path.name}"
        output_dir = tmp_path / "tiles_output_remote"
        config_path = tmp_path / "config_remote.yaml"
        config_path.write_text(
            f"""
inputs:
  gpkg_path: {archive_url}
  layer: surfaces
  building_id_field: building_id
  class_field: surface_type
tiling:
  tile_size: 250.0
  overwrite: true
artifacts:
  output_dir: {output_dir}
""".strip(),
            encoding="utf-8",
        )

        cfg = PipelineConfig.from_yaml(config_path)
        metrics = run_pipeline(cfg)
    finally:
        server.shutdown()
        thread.join()
        with contextlib.suppress(OSError):
            server.server_close()

    assert metrics.tile_count == 1
    tileset = json.loads(metrics.tileset_path.read_text(encoding="utf-8"))
    assert tileset["asset"]["version"] == "1.1"
    assert metrics.output_dir == output_dir
