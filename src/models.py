from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(slots=True, frozen=True)
class MaterialStyle:
    key: str
    name: str
    base_color_factor: tuple[float, float, float, float]


@dataclass(slots=True)
class SurfaceFeature:
    source_id: str
    group_id: str
    semantic_class: str
    exterior: np.ndarray
    holes: list[np.ndarray]
    centroid_xy: np.ndarray
    properties: dict[str, str]
    source_class: str | None = None


@dataclass(slots=True)
class TileInfo:
    key: tuple[int, int]
    uri: str
    region: list[float]
    transform: list[float]
    feature_count: int


@dataclass(slots=True)
class PipelineMetrics:
    tileset_path: Path
    output_dir: Path
    tile_count: int
