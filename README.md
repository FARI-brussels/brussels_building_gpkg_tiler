# gpkg_tiler

Config-driven exporter for tiling 3D polygon surfaces from a GeoPackage into
OGC 3D Tiles 1.1 with `.glb` tile content.

## Run

Install dependencies:

```bash
uv sync --extra dev
```

Generate a starter config:

```bash
uv run gpkg-tiler init-config
```

Run the pipeline:

```bash
uv run gpkg-tiler run --config configs/full-bx-buildings.yaml
```

The CLI currently exposes two commands:

- `gpkg-tiler init-config` writes a starter YAML to `configs/default.yaml` by default
- `gpkg-tiler run --config <path>` loads a YAML file and exports a tileset

## Config Format

The runtime config is defined in [`src/config.py`](/home/mrcyme/Documents/FARI/smartcity/gpkg_tiler/src/config.py).

```yaml
inputs:
  gpkg_path: input/saintjosse.gpkg
  layer: BuildingFaces
  building_id_field: BUSOLID_ID
  class_field: TYPE
  default_class: default

tiling:
  tile_size: 800
  root_geometric_error:
  no_elevation: true
  with_metadata: true
  overwrite: true

artifacts:
  output_dir: output/test

styles:
  class_colors:
    GROUNDSURFACE: "#C8E8B0"
    OUTERCEILING: "#D8DDE6"
    OUTERFLOOR: "#B8A37A"
    ROOFSURFACE: "#CC2222"
    WALLSURFACE: "#888888"
```

### `inputs`

- `gpkg_path`: required. Supports a local `.gpkg`, a local `.zip` containing exactly one `.gpkg`, or a `file:`, `http:`, or `https:` URL pointing to either of those.
- `layer`: optional. If the GeoPackage has multiple layers and this is omitted, the run fails.
- `building_id_field`: optional. Groups surfaces into a single building or object before tile assignment. If omitted, each source row is treated as its own group.
- `class_field`: optional. Source field used to derive semantic classes and style selection.
- `default_class`: optional, default `default`. Used when `class_field` is missing, empty, or not recognized by the class normalizer.

### `tiling`

- `tile_size`: optional, default `250.0`. Tile assignment grid size in source CRS units. Must be greater than `0`.
- `root_geometric_error`: optional. If omitted or `null`, the tileset root geometric error falls back to `tile_size`.
- `no_elevation`: optional, default `false`. Normalizes each grouped object so its minimum Z becomes `0` and disables the CRS elevation offset.
- `with_metadata`: optional, default `false`. Embeds per-feature metadata in the GLB using `EXT_mesh_features` and `EXT_structural_metadata`.
- `overwrite`: optional, default `false`. Allows writing into a non-empty output directory. It does not clean old files first.

### `artifacts`

- `output_dir`: optional, default `output`. Directory where `tileset.json` and `tiles/*.glb` are written.

### `styles`

- `class_colors`: optional. Hex colors in `#RRGGBB` format.

Color lookup works in two passes:

- first by exact source class value from `class_field`
- then by normalized semantic class such as `wall`, `roof`, `ground`, `window`, `door`, `tree_canopy`, `tree_trunk`, or `default`

## Included Configs

The repository currently ships these example configs:

- [`configs/full-bx-buildings.yaml`](/home/mrcyme/Documents/FARI/smartcity/gpkg_tiler/configs/full-bx-buildings.yaml): remote Brussels dataset, `BuildingFaces` layer, metadata enabled, `no_elevation: true`, output to `output/full-bx`
- [`configs/full-bx-building-no-elevation.yaml`](/home/mrcyme/Documents/FARI/smartcity/gpkg_tiler/configs/full-bx-building-no-elevation.yaml): remote Brussels dataset, `BuildingFaces` layer, metadata enabled, `no_elevation: true`, output to `output/full-bx-no-elevation`
- [`configs/full-bx-engineeringwork.yaml`](/home/mrcyme/Documents/FARI/smartcity/gpkg_tiler/configs/full-bx-engineeringwork.yaml): remote Brussels dataset, `EngineeringWorkFaces` layer, metadata enabled, `no_elevation: true`, output to `output/full-bx`
- [`configs/full-bx-engineeringwork-no-elevation.yaml`](/home/mrcyme/Documents/FARI/smartcity/gpkg_tiler/configs/full-bx-engineeringwork-no-elevation.yaml): remote Brussels dataset, `EngineeringWorkFaces` layer, metadata enabled, `no_elevation: true`, output to `output/full-bx-no-elevation`
- [`configs/test-engineeringworks.yaml`](/home/mrcyme/Documents/FARI/smartcity/gpkg_tiler/configs/test-engineeringworks.yaml): local test input `input/saintjosse.gpkg`, `EngineeringWorkFaces` layer, metadata enabled, `no_elevation: true`, output to `output/test`
- [`configs/test -building.yaml`](/home/mrcyme/Documents/FARI/smartcity/gpkg_tiler/configs/test%20-building.yaml): local test input `input/saintjosse.gpkg`, `EngineeringWorkFaces` layer, metadata enabled, `no_elevation: true`, output to `output/test`

The shipped presets currently differ mostly by input source, layer name, and output directory. They do not currently provide both elevated and non-elevated variants for the same dataset; the checked-in presets all set `no_elevation: true`.

## Runtime Notes

- Relative paths are resolved from the current working directory, not from the directory containing the YAML file.
- Local or downloaded ZIP archives must contain exactly one `.gpkg` file.
- `building_id_field` and `class_field` matching is case-insensitive against available columns.
- Input geometry must contain polygonal surfaces (`Polygon` or `MultiPolygon`).
- If the output directory is non-empty and `overwrite` is `false`, the export fails with `FileExistsError`.


