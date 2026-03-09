from __future__ import annotations

import json
from collections.abc import Callable

from src.config import PipelineConfig
from src.io.tiles_writer import write_3d_tiles
from src.models import PipelineMetrics


def run_pipeline(
    cfg: PipelineConfig,
    *,
    progress: Callable[[str], None] | None = None,
) -> PipelineMetrics:
    if progress is not None:
        progress(
            "Running export with "
            f"gpkg={cfg.inputs.gpkg_path} "
            f"output={cfg.artifacts.output_dir}"
        )
    tileset_path = write_3d_tiles(cfg, progress=progress)
    tileset = json.loads(tileset_path.read_text(encoding="utf-8"))
    tile_count = len(tileset.get("root", {}).get("children", []))
    if progress is not None:
        progress(f"Tileset ready with {tile_count} tile(s): {tileset_path}")
    return PipelineMetrics(
        tileset_path=tileset_path,
        output_dir=cfg.artifacts.output_dir,
        tile_count=tile_count,
    )
