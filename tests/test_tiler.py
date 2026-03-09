from __future__ import annotations

import json
import struct
from pathlib import Path

import geopandas as gpd
import numpy as np
from shapely.geometry import Polygon

from gpkg_tiler.models import SurfaceFeature
from gpkg_tiler.tiler import _normalize_group_elevation_to_zero, export_gpkg_to_3d_tiles


def _load_glb_json(glb_path: Path) -> dict:
    data = glb_path.read_bytes()
    magic, version, _length = struct.unpack_from("<4sII", data, 0)
    assert magic == b"glTF"
    assert version == 2

    offset = 12
    json_length, json_chunk_type = struct.unpack_from("<II", data, offset)
    assert json_chunk_type == 0x4E4F534A
    offset += 8
    return json.loads(data[offset : offset + json_length].decode("utf-8").rstrip(" "))


def test_export_gpkg_to_3d_tiles(tmp_path: Path) -> None:
    gpkg_path = tmp_path / "surfaces.gpkg"
    output_dir = tmp_path / "tiles_output"

    wall = Polygon(
        [
            (0.0, 0.0, 0.0),
            (0.0, 0.0, 3.0),
            (4.0, 0.0, 3.0),
            (4.0, 0.0, 0.0),
            (0.0, 0.0, 0.0),
        ]
    )
    roof = Polygon(
        [
            (0.0, 0.0, 3.0),
            (4.0, 0.0, 3.0),
            (4.0, 4.0, 3.0),
            (0.0, 4.0, 3.0),
            (0.0, 0.0, 3.0),
        ]
    )
    gdf = gpd.GeoDataFrame(
        {
            "building_id": ["bldg-1", "bldg-1"],
            "surface_type": ["WallSurface", "RoofSurface"],
            "geometry": [wall, roof],
        },
        crs="EPSG:31370",
    )
    gdf.to_file(gpkg_path, layer="surfaces", driver="GPKG")

    tileset_path = export_gpkg_to_3d_tiles(
        gpkg_path,
        output_dir,
        layer="surfaces",
        building_id_field="building_id",
        class_field="surface_type",
    )

    tileset = json.loads(tileset_path.read_text(encoding="utf-8"))
    assert tileset["asset"]["version"] == "1.1"
    assert tileset["root"]["children"]

    child = tileset["root"]["children"][0]
    glb_path = output_dir / child["content"]["uri"]
    assert glb_path.exists()

    gltf = _load_glb_json(glb_path)
    assert gltf["asset"]["version"] == "2.0"
    assert len(gltf["materials"]) == 2
    assert all(material.get("doubleSided") is True for material in gltf["materials"])

    for primitive in gltf["meshes"][0]["primitives"]:
        attrs = primitive["attributes"]
        assert "POSITION" in attrs
        assert "NORMAL" in attrs
        assert "COLOR_0" not in attrs
        assert "_FEATURE_ID_0" not in attrs


def test_normalize_group_elevation_to_zero() -> None:
    surfaces = [
        SurfaceFeature(
            source_id="a1",
            group_id="a",
            semantic_class="wall",
            exterior=np.asarray(
                [
                    [0.0, 0.0, 5.0],
                    [1.0, 0.0, 5.0],
                    [1.0, 0.0, 8.0],
                    [0.0, 0.0, 8.0],
                    [0.0, 0.0, 5.0],
                ],
                dtype=float,
            ),
            holes=[],
            centroid_xy=np.asarray([0.5, 0.0], dtype=float),
            properties={},
        ),
        SurfaceFeature(
            source_id="a2",
            group_id="a",
            semantic_class="roof",
            exterior=np.asarray(
                [
                    [0.0, 0.0, 8.0],
                    [1.0, 0.0, 8.0],
                    [1.0, 1.0, 8.0],
                    [0.0, 1.0, 8.0],
                    [0.0, 0.0, 8.0],
                ],
                dtype=float,
            ),
            holes=[],
            centroid_xy=np.asarray([0.5, 0.5], dtype=float),
            properties={},
        ),
        SurfaceFeature(
            source_id="b1",
            group_id="b",
            semantic_class="wall",
            exterior=np.asarray(
                [
                    [0.0, 0.0, 12.0],
                    [1.0, 0.0, 12.0],
                    [1.0, 0.0, 15.0],
                    [0.0, 0.0, 15.0],
                    [0.0, 0.0, 12.0],
                ],
                dtype=float,
            ),
            holes=[],
            centroid_xy=np.asarray([0.5, 0.0], dtype=float),
            properties={},
        ),
    ]

    normalized = _normalize_group_elevation_to_zero(surfaces)
    by_group: dict[str, list[SurfaceFeature]] = {}
    for surface in normalized:
        by_group.setdefault(surface.group_id, []).append(surface)

    assert min(surface.exterior[:, 2].min() for surface in by_group["a"]) == 0.0
    assert min(surface.exterior[:, 2].min() for surface in by_group["b"]) == 0.0
    assert max(surface.exterior[:, 2].max() for surface in by_group["a"]) == 3.0
    assert max(surface.exterior[:, 2].max() for surface in by_group["b"]) == 3.0


def test_export_gpkg_to_3d_tiles_with_metadata(tmp_path: Path) -> None:
    gpkg_path = tmp_path / "surfaces.gpkg"
    output_dir = tmp_path / "tiles_output_metadata"

    wall = Polygon(
        [
            (0.0, 0.0, 0.0),
            (0.0, 0.0, 3.0),
            (4.0, 0.0, 3.0),
            (4.0, 0.0, 0.0),
            (0.0, 0.0, 0.0),
        ]
    )
    roof = Polygon(
        [
            (0.0, 0.0, 3.0),
            (4.0, 0.0, 3.0),
            (4.0, 4.0, 3.0),
            (0.0, 4.0, 3.0),
            (0.0, 0.0, 3.0),
        ]
    )
    gdf = gpd.GeoDataFrame(
        {
            "building_id": ["bldg-1", "bldg-1"],
            "surface_type": ["WallSurface", "RoofSurface"],
            "geometry": [wall, roof],
        },
        crs="EPSG:31370",
    )
    gdf.to_file(gpkg_path, layer="surfaces", driver="GPKG")

    tileset_path = export_gpkg_to_3d_tiles(
        gpkg_path,
        output_dir,
        layer="surfaces",
        building_id_field="building_id",
        class_field="surface_type",
        with_metadata=True,
    )

    child = json.loads(tileset_path.read_text(encoding="utf-8"))["root"]["children"][0]
    gltf = _load_glb_json(output_dir / child["content"]["uri"])
    assert "extensionsUsed" in gltf
    assert "EXT_mesh_features" in gltf["extensionsUsed"]
    assert "EXT_structural_metadata" in gltf["extensionsUsed"]
    assert "extensions" in gltf
    assert "EXT_structural_metadata" in gltf["extensions"]
    assert any("_FEATURE_ID_0" in primitive["attributes"] for primitive in gltf["meshes"][0]["primitives"])


def test_export_gpkg_to_3d_tiles_with_class_color_mapping(tmp_path: Path) -> None:
    gpkg_path = tmp_path / "surfaces_colors.gpkg"
    output_dir = tmp_path / "tiles_output_colors"

    wall = Polygon(
        [
            (0.0, 0.0, 0.0),
            (0.0, 0.0, 3.0),
            (4.0, 0.0, 3.0),
            (4.0, 0.0, 0.0),
            (0.0, 0.0, 0.0),
        ]
    )
    roof = Polygon(
        [
            (0.0, 0.0, 3.0),
            (4.0, 0.0, 3.0),
            (4.0, 4.0, 3.0),
            (0.0, 4.0, 3.0),
            (0.0, 0.0, 3.0),
        ]
    )
    gdf = gpd.GeoDataFrame(
        {
            "building_id": ["bldg-1", "bldg-1"],
            "surface_type": ["WALLSURFACE", "ROOFSURFACE"],
            "geometry": [wall, roof],
        },
        crs="EPSG:31370",
    )
    gdf.to_file(gpkg_path, layer="surfaces", driver="GPKG")

    tileset_path = export_gpkg_to_3d_tiles(
        gpkg_path,
        output_dir,
        layer="surfaces",
        building_id_field="building_id",
        class_field="surface_type",
        class_colors={
            "WALLSURFACE": "#112233",
            "ROOFSURFACE": "#445566",
        },
    )

    child = json.loads(tileset_path.read_text(encoding="utf-8"))["root"]["children"][0]
    gltf = _load_glb_json(output_dir / child["content"]["uri"])
    materials = {material["name"]: material for material in gltf["materials"]}
    assert materials["WALLSURFACE"]["pbrMetallicRoughness"]["baseColorFactor"] == [
        17 / 255.0,
        34 / 255.0,
        51 / 255.0,
        1.0,
    ]
    assert materials["ROOFSURFACE"]["pbrMetallicRoughness"]["baseColorFactor"] == [
        68 / 255.0,
        85 / 255.0,
        102 / 255.0,
        1.0,
    ]
