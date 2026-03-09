from __future__ import annotations

from pathlib import Path

import typer
import yaml

from src.config import InputConfig, PipelineConfig, StyleConfig
from src.pipeline.runner import run_pipeline

app = typer.Typer(help="Tile a GeoPackage into OGC 3D Tiles 1.1 using YAML configs.")


@app.command("run")
def run(
    config: Path = typer.Option(..., "--config", "-c", exists=True, file_okay=True, dir_okay=False),
) -> None:
    cfg = PipelineConfig.from_yaml(config)
    metrics = run_pipeline(cfg)
    typer.echo(
        "Export finished. "
        f"tiles={metrics.tile_count} "
        f"tileset={metrics.tileset_path}"
    )


@app.command("init-config")
def init_config(path: Path = typer.Option(Path("configs/default.yaml"), "--path", "-p")) -> None:
    cfg = PipelineConfig(
        inputs=InputConfig(
            gpkg_path=Path("data/surfaces.gpkg"),
            layer="surfaces",
            building_id_field="building_id",
            class_field="surface_type",
        ),
        styles=StyleConfig(),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(cfg.to_dict(), sort_keys=False), encoding="utf-8")
    typer.echo(f"Wrote {path}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
