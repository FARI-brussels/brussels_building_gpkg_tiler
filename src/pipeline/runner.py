from __future__ import annotations

import json

from src.config import PipelineConfig
from src.io.tiles_writer import write_3d_tiles
from src.models import PipelineMetrics


def run_pipeline(cfg: PipelineConfig) -> PipelineMetrics:
    tileset_path = write_3d_tiles(cfg)
    tileset = json.loads(tileset_path.read_text(encoding="utf-8"))
    tile_count = len(tileset.get("root", {}).get("children", []))
    return PipelineMetrics(
        tileset_path=tileset_path,
        output_dir=cfg.artifacts.output_dir,
        tile_count=tile_count,
    )
