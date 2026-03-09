from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class PipelineMetrics:
    tileset_path: Path
    output_dir: Path
    tile_count: int

