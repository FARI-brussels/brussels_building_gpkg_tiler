from __future__ import annotations

from pathlib import Path

import typer

from src.gpkg_tiler.urbis_feed import run_urbis_feed_pipeline

app = typer.Typer(help="Download the latest Brussels UrbIS GeoPackage and export tile variants.")


@app.command("run")
def run(
    feed: str = typer.Argument(..., help="Atom feed URL or local XML path."),
    output_dir: Path = typer.Argument(..., help="Directory for the downloaded source and tile outputs."),
    layer: str | None = typer.Option(None, "--layer"),
    building_id_field: str | None = typer.Option(None, "--building-id-field"),
    class_field: str | None = typer.Option(None, "--class-field"),
    default_class: str = typer.Option("default", "--default-class"),
    tile_size: float = typer.Option(250.0, "--tile-size"),
    root_geometric_error: float | None = typer.Option(None, "--root-geometric-error"),
    with_metadata: bool = typer.Option(False, "--with-metadata"),
    overwrite: bool = typer.Option(False, "--overwrite"),
) -> None:
    result = run_urbis_feed_pipeline(
        feed,
        output_dir,
        layer=layer,
        building_id_field=building_id_field,
        class_field=class_field,
        default_class=default_class,
        tile_size=tile_size,
        root_geometric_error=root_geometric_error,
        with_metadata=with_metadata,
        overwrite=overwrite,
    )
    typer.echo(
        "UrbIS export finished. "
        f"gpkg={result.gpkg_path} "
        f"with_elevation={result.with_elevation_tileset} "
        f"no_elevation={result.no_elevation_tileset}"
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
