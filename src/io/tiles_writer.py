from __future__ import annotations

from pathlib import Path

from src.config import PipelineConfig
from src.io.input_resolver import resolve_gpkg_input
from src.tiler import export_gpkg_to_3d_tiles


def write_3d_tiles(cfg: PipelineConfig) -> Path:
    with resolve_gpkg_input(cfg.inputs.gpkg_path) as gpkg_path:
        return export_gpkg_to_3d_tiles(
            gpkg_path,
            cfg.artifacts.output_dir,
            layer=cfg.inputs.layer,
            building_id_field=cfg.inputs.building_id_field,
            class_field=cfg.inputs.class_field,
            default_class=cfg.inputs.default_class,
            tile_size=cfg.tiling.tile_size,
            root_geometric_error=cfg.tiling.root_geometric_error,
            no_elevation=cfg.tiling.no_elevation,
            with_metadata=cfg.tiling.with_metadata,
            class_colors=cfg.styles.class_colors,
            overwrite=cfg.tiling.overwrite,
        )
