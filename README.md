# gpkg_tiler

Config-driven exporter for tiling a GeoPackage of 3D polygon surfaces into
OGC 3D Tiles 1.1 with `.glb` tile content.

The repo now follows the same layout pattern as `lod3-facade-extraction`:

- `main.py` for the root entrypoint
- `configs/*.yaml` for runnable settings
- `src/config.py` for typed runtime config
- `src/pipeline/runner.py` for orchestration
- `src/io/` for thin adapters
- `src/cli.py` for the Typer command layer
- `src/gpkg_tiler/` for the existing tiling/export core

## Run

```bash
uv sync --extra dev
uv run gpkg-tiler run --config configs/default.yaml
```

Create a starter config:

```bash
uv run gpkg-tiler init-config --path configs/local.yaml
```

Example config variants included in this repo:

- `configs/no-elevation.yaml`
- `configs/with-metadata.yaml`
- `configs/test.yaml`

You can override GLB material colors per raw `class_field` value:

```yaml
styles:
  class_colors:
    GROUNDSURFACE: "#C8E8B0"
    OUTERCEILING: "#D8DDE6"
    OUTERFLOOR: "#B8A37A"
    ROOFSURFACE: "#CC2222"
    WALLSURFACE: "#888888"
```

## Notes

- Input features must be `Polygon` or `MultiPolygon`
- Missing semantic classes fall back to `default`
- For `EPSG:31370`, the exporter applies a local TAW to ellipsoidal offset
- Metadata embedding is optional and can be enabled per config with `with_metadata: true`
