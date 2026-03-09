from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CLASS_COLORS: dict[str, str] = {
    "GROUNDSURFACE": "#C8E8B0",
    "OUTERCEILING": "#D8DDE6",
    "OUTERFLOOR": "#B8A37A",
    "ROOFSURFACE": "#CC2222",
    "WALLSURFACE": "#888888",
}


@dataclass(slots=True)
class InputConfig:
    gpkg_path: Path
    layer: str | None = None
    building_id_field: str | None = None
    class_field: str | None = None
    default_class: str = "default"


@dataclass(slots=True)
class TilingConfig:
    tile_size: float = 250.0
    root_geometric_error: float | None = None
    no_elevation: bool = False
    with_metadata: bool = False
    overwrite: bool = False


@dataclass(slots=True)
class ArtifactConfig:
    output_dir: Path = Path("output")


@dataclass(slots=True)
class StyleConfig:
    class_colors: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_CLASS_COLORS))


@dataclass(slots=True)
class PipelineConfig:
    inputs: InputConfig
    tiling: TilingConfig = field(default_factory=TilingConfig)
    artifacts: ArtifactConfig = field(default_factory=ArtifactConfig)
    styles: StyleConfig = field(default_factory=StyleConfig)

    @classmethod
    def from_yaml(cls, path: Path) -> "PipelineConfig":
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        inputs = data.get("inputs", {})
        artifacts = data.get("artifacts", {})
        styles = data.get("styles", {})
        return cls(
            inputs=InputConfig(
                gpkg_path=Path(inputs["gpkg_path"]),
                layer=inputs.get("layer"),
                building_id_field=inputs.get("building_id_field"),
                class_field=inputs.get("class_field"),
                default_class=inputs.get("default_class", "default"),
            ),
            tiling=TilingConfig(**data.get("tiling", {})),
            artifacts=ArtifactConfig(
                output_dir=Path(artifacts.get("output_dir", "output")),
            ),
            styles=StyleConfig(
                class_colors={
                    key: str(value)
                    for key, value in styles.get("class_colors", DEFAULT_CLASS_COLORS).items()
                }
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "inputs": {
                "gpkg_path": str(self.inputs.gpkg_path),
                "layer": self.inputs.layer,
                "building_id_field": self.inputs.building_id_field,
                "class_field": self.inputs.class_field,
                "default_class": self.inputs.default_class,
            },
            "tiling": {
                "tile_size": self.tiling.tile_size,
                "root_geometric_error": self.tiling.root_geometric_error,
                "no_elevation": self.tiling.no_elevation,
                "with_metadata": self.tiling.with_metadata,
                "overwrite": self.tiling.overwrite,
            },
            "artifacts": {
                "output_dir": str(self.artifacts.output_dir),
            },
            "styles": {
                "class_colors": dict(self.styles.class_colors),
            },
        }
