from __future__ import annotations

import json
from pathlib import Path

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
