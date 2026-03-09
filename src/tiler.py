from __future__ import annotations

import json
import math
import struct
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np
from pyproj import CRS, Transformer

from .gpkg_reader import read_surfaces
from .models import MaterialStyle, SurfaceFeature, TileInfo

_ARRAY_BUFFER = 34962
_ELEMENT_ARRAY_BUFFER = 34963
_FLOAT = 5126
_UNSIGNED_INT = 5125

_CLASS_STYLES: dict[str, MaterialStyle] = {
    "wall": MaterialStyle("wall", "Wall", (136.0 / 255.0, 136.0 / 255.0, 136.0 / 255.0, 1.0)),
    "roof": MaterialStyle("roof", "Roof", (204.0 / 255.0, 34.0 / 255.0, 34.0 / 255.0, 1.0)),
    "window": MaterialStyle("window", "Window", (80.0 / 255.0, 150.0 / 255.0, 220.0 / 255.0, 1.0)),
    "door": MaterialStyle("door", "Door", (17.0 / 255.0, 17.0 / 255.0, 17.0 / 255.0, 1.0)),
    "ground": MaterialStyle("ground", "Ground", (200.0 / 255.0, 232.0 / 255.0, 176.0 / 255.0, 1.0)),
    "tree_canopy": MaterialStyle("tree_canopy", "TreeCanopy", (34.0 / 255.0, 139.0 / 255.0, 34.0 / 255.0, 1.0)),
    "tree_trunk": MaterialStyle("tree_trunk", "TreeTrunk", (101.0 / 255.0, 67.0 / 255.0, 33.0 / 255.0, 1.0)),
    "default": MaterialStyle("default", "Default", (176.0 / 255.0, 176.0 / 255.0, 176.0 / 255.0, 1.0)),
}


def _hex_to_rgba(color: str) -> tuple[float, float, float, float]:
    value = color.strip().lstrip("#")
    if len(value) != 6:
        raise ValueError(f"Invalid color '{color}'. Expected #RRGGBB.")
    rgb = tuple(int(value[index : index + 2], 16) / 255.0 for index in range(0, 6, 2))
    return (rgb[0], rgb[1], rgb[2], 1.0)


def _build_class_styles(class_colors: dict[str, str] | None) -> dict[str, MaterialStyle]:
    styles = dict(_CLASS_STYLES)
    if not class_colors:
        return styles

    for class_name, color in class_colors.items():
        key = str(class_name).strip()
        if not key:
            continue
        styles[key] = MaterialStyle(key=key, name=key, base_color_factor=_hex_to_rgba(str(color)))
    return styles


def _style_for_class(style_key: str, class_styles: dict[str, MaterialStyle]) -> MaterialStyle:
    return class_styles.get(style_key, class_styles["default"])


def _style_key_for_surface(surface: SurfaceFeature, class_styles: dict[str, MaterialStyle]) -> str:
    if surface.source_class:
        source_class = surface.source_class.strip()
        if source_class in class_styles:
            return source_class
    if surface.semantic_class in class_styles:
        return surface.semantic_class
    return "default"


def _pad4(data: bytes, pad_byte: bytes = b"\x00") -> bytes:
    remainder = len(data) % 4
    return data if remainder == 0 else data + pad_byte * (4 - remainder)


def _append_aligned(blob: bytes, payload: bytes, alignment: int = 4) -> tuple[bytes, int]:
    padding = (-len(blob)) % alignment
    if padding:
        blob += b"\x00" * padding
    offset = len(blob)
    blob += payload
    return blob, offset


def _write_glb(path: Path, gltf_json: dict[str, Any], bin_chunk: bytes) -> None:
    json_bytes = json.dumps(gltf_json, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    json_bytes = _pad4(json_bytes, pad_byte=b" ")
    bin_chunk = _pad4(bin_chunk)

    payload = bytearray()
    payload += struct.pack("<II", len(json_bytes), 0x4E4F534A)
    payload += json_bytes
    payload += struct.pack("<II", len(bin_chunk), 0x004E4942)
    payload += bin_chunk

    header = struct.pack("<4sII", b"glTF", 2, 12 + len(payload))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + payload)


def _build_local_coordinate_system(
    normal: np.ndarray, origin: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    z_axis = normal / np.linalg.norm(normal)
    global_z = np.array([0.0, 0.0, 1.0], dtype=float)
    x_axis = np.cross(z_axis, global_z)
    if np.linalg.norm(x_axis) < 1e-8:
        x_axis = np.cross(z_axis, np.array([0.0, 1.0, 0.0], dtype=float))
    x_axis = x_axis / np.linalg.norm(x_axis)
    y_axis = np.cross(x_axis, z_axis)
    y_axis = y_axis / np.linalg.norm(y_axis)
    return x_axis, y_axis, z_axis, origin


def _polygon_normal(coords: np.ndarray) -> np.ndarray:
    normal = np.zeros(3, dtype=float)
    for index in range(len(coords) - 1):
        p = coords[index]
        q = coords[index + 1]
        normal[0] += (p[1] - q[1]) * (p[2] + q[2])
        normal[1] += (p[2] - q[2]) * (p[0] + q[0])
        normal[2] += (p[0] - q[0]) * (p[1] + q[1])
    magnitude = np.linalg.norm(normal)
    if magnitude == 0:
        return np.array([0.0, 0.0, 1.0], dtype=float)
    return normal / magnitude


def _to_local_xy(
    coords_3d: np.ndarray,
    x_axis: np.ndarray,
    y_axis: np.ndarray,
    origin: np.ndarray,
) -> np.ndarray:
    diffs = coords_3d - origin
    return np.column_stack([diffs @ x_axis, diffs @ y_axis])


def _from_local_xy(
    coords_xy: np.ndarray,
    x_axis: np.ndarray,
    y_axis: np.ndarray,
    origin: np.ndarray,
) -> np.ndarray:
    return origin + coords_xy[:, 0][:, None] * x_axis + coords_xy[:, 1][:, None] * y_axis


def _strip_closing_vertex(ring: np.ndarray) -> np.ndarray:
    if len(ring) > 1 and np.allclose(ring[0], ring[-1]):
        return ring[:-1]
    return ring


def _triangulate_surface(surface: SurfaceFeature) -> list[np.ndarray]:
    import mapbox_earcut as earcut

    normal = _polygon_normal(surface.exterior)
    x_axis, y_axis, _z_axis, origin = _build_local_coordinate_system(normal, surface.exterior[0])

    rings = [_strip_closing_vertex(_to_local_xy(surface.exterior, x_axis, y_axis, origin))]
    for hole in surface.holes:
        ring = _strip_closing_vertex(_to_local_xy(hole, x_axis, y_axis, origin))
        if len(ring) >= 3:
            rings.append(ring)

    if not rings or len(rings[0]) < 3:
        return []

    vertices = np.vstack(rings).astype(np.float64)
    ring_lengths = np.cumsum([len(ring) for ring in rings], dtype=np.uint32)
    indices = earcut.triangulate_float64(vertices, ring_lengths)
    if len(indices) == 0:
        return []

    triangles: list[np.ndarray] = []
    for start in range(0, len(indices), 3):
        tri_xy = vertices[indices[start : start + 3]]
        triangles.append(_from_local_xy(tri_xy, x_axis, y_axis, origin))
    return triangles


def _make_transformers(crs: CRS) -> tuple[Transformer, Transformer]:
    ecef = CRS.from_epsg(4978)
    wgs84 = CRS.from_epsg(4326)
    return (
        Transformer.from_crs(crs, ecef, always_xy=True),
        Transformer.from_crs(ecef, wgs84, always_xy=True),
    )


def _compute_taw_to_ellipsoidal_offset() -> float:
    """Approximate Brussels TAW/Ostend height to ellipsoidal height offset.

    UrbIS building Z values are carried in TAW while the layer advertises only
    EPSG:31370 horizontally. 3D Tiles placement needs ellipsoidal heights for
    the ECEF transform, so we estimate the local geoid undulation once using
    the compound CRS EPSG:6190 (BD72 / Belgian Lambert 72 + Ostend height).
    Across Brussels this offset is effectively constant for this export scale.
    """
    try:
        import pyproj

        pyproj.network.set_network_enabled(True)
        transformer = pyproj.Transformer.from_crs("EPSG:6190", "EPSG:4979", always_xy=True)
        _lon, _lat, ellipsoidal_height = transformer.transform(150000.0, 170000.0, 0.0)
        return float(ellipsoidal_height)
    except Exception:
        return 0.0


def _source_z_to_ellipsoidal_offset(crs: CRS) -> float:
    authority = crs.to_authority()
    if authority == ("EPSG", "31370"):
        return _compute_taw_to_ellipsoidal_offset()
    return 0.0


def _points_to_ecef(
    points: np.ndarray,
    transformer: Transformer,
    z_offset: float = 0.0,
) -> np.ndarray:
    z_values = points[:, 2] + z_offset
    x, y, z = transformer.transform(points[:, 0], points[:, 1], z_values)
    return np.column_stack([x, y, z]).astype(np.float64)


def _ecef_to_enu_batch(
    ecef_points: np.ndarray,
    origin_ecef: np.ndarray,
    lon: float,
    lat: float,
) -> np.ndarray:
    lon_radians = math.radians(lon)
    lat_radians = math.radians(lat)
    sin_lon = math.sin(lon_radians)
    cos_lon = math.cos(lon_radians)
    sin_lat = math.sin(lat_radians)
    cos_lat = math.cos(lat_radians)

    delta = ecef_points - origin_ecef
    east = -sin_lon * delta[:, 0] + cos_lon * delta[:, 1]
    north = -sin_lat * cos_lon * delta[:, 0] - sin_lat * sin_lon * delta[:, 1] + cos_lat * delta[:, 2]
    up = cos_lat * cos_lon * delta[:, 0] + cos_lat * sin_lon * delta[:, 1] + sin_lat * delta[:, 2]
    return np.column_stack([east, north, up])


def _enu_to_ecef_point(
    enu: np.ndarray,
    origin_ecef: np.ndarray,
    lon: float,
    lat: float,
) -> np.ndarray:
    lon_radians = math.radians(lon)
    lat_radians = math.radians(lat)
    sin_lon = math.sin(lon_radians)
    cos_lon = math.cos(lon_radians)
    sin_lat = math.sin(lat_radians)
    cos_lat = math.cos(lat_radians)

    east, north, up = float(enu[0]), float(enu[1]), float(enu[2])
    dx = -sin_lon * east - sin_lat * cos_lon * north + cos_lat * cos_lon * up
    dy = cos_lon * east - sin_lat * sin_lon * north + cos_lat * sin_lon * up
    dz = cos_lat * north + sin_lat * up
    return origin_ecef + np.array([dx, dy, dz], dtype=float)


def _enu_to_ecef_transform(lon: float, lat: float, origin_ecef: np.ndarray) -> list[float]:
    lon_radians = math.radians(lon)
    lat_radians = math.radians(lat)
    sin_lon = math.sin(lon_radians)
    cos_lon = math.cos(lon_radians)
    sin_lat = math.sin(lat_radians)
    cos_lat = math.cos(lat_radians)
    tx, ty, tz = origin_ecef.tolist()

    return [
        -sin_lon, cos_lon, 0.0, 0.0,
        -sin_lat * cos_lon, -sin_lat * sin_lon, cos_lat, 0.0,
        cos_lat * cos_lon, cos_lat * sin_lon, sin_lat, 0.0,
        tx, ty, tz, 1.0,
    ]


def _bounding_region(
    enu_min: np.ndarray,
    enu_max: np.ndarray,
    origin_ecef: np.ndarray,
    lon: float,
    lat: float,
    ecef_to_wgs84: Transformer,
) -> list[float]:
    lons: list[float] = []
    lats: list[float] = []
    heights: list[float] = []
    for east in (enu_min[0], enu_max[0]):
        for north in (enu_min[1], enu_max[1]):
            for up in (enu_min[2], enu_max[2]):
                point_ecef = _enu_to_ecef_point(np.array([east, north, up]), origin_ecef, lon, lat)
                point_lon, point_lat, point_height = ecef_to_wgs84.transform(
                    point_ecef[0], point_ecef[1], point_ecef[2]
                )
                lons.append(point_lon)
                lats.append(point_lat)
                heights.append(point_height)
    return [
        math.radians(min(lons)),
        math.radians(min(lats)),
        math.radians(max(lons)),
        math.radians(max(lats)),
        min(heights),
        max(heights),
    ]


def _triangle_normal(triangle: np.ndarray) -> np.ndarray:
    normal = np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])
    magnitude = np.linalg.norm(normal)
    if magnitude == 0:
        return np.array([0.0, 1.0, 0.0], dtype=np.float32)
    return (normal / magnitude).astype(np.float32)


def _build_glb_for_tile(
    triangles_y_up: list[np.ndarray],
    triangle_style_keys: list[str],
    triangle_feature_ids: list[int],
    feature_properties: list[dict[str, str]],
    output_path: Path,
    with_metadata: bool,
    class_styles: dict[str, MaterialStyle],
) -> None:
    per_class_positions: dict[str, list[list[float]]] = defaultdict(list)
    per_class_normals: dict[str, list[list[float]]] = defaultdict(list)
    per_class_indices: dict[str, list[int]] = defaultdict(list)
    per_class_feature_ids: dict[str, list[int]] = defaultdict(list)

    for triangle, style_key, feature_id in zip(
        triangles_y_up,
        triangle_style_keys,
        triangle_feature_ids,
        strict=True,
    ):
        normal = _triangle_normal(triangle)
        base_index = len(per_class_positions[style_key])
        for vertex in triangle:
            per_class_positions[style_key].append(vertex.astype(np.float32).tolist())
            per_class_normals[style_key].append(normal.tolist())
            per_class_feature_ids[style_key].append(feature_id)
        per_class_indices[style_key].extend([base_index, base_index + 1, base_index + 2])

    materials: list[dict[str, Any]] = []
    buffer_views: list[dict[str, Any]] = []
    accessors: list[dict[str, Any]] = []
    primitives: list[dict[str, Any]] = []
    binary_blob = b""

    ordered_classes = sorted(per_class_positions.keys(), key=lambda value: _style_for_class(value, class_styles).name)
    for style_key in ordered_classes:
        positions = np.asarray(per_class_positions[style_key], dtype=np.float32)
        normals = np.asarray(per_class_normals[style_key], dtype=np.float32)
        indices = np.asarray(per_class_indices[style_key], dtype=np.uint32)
        if len(positions) == 0 or len(indices) == 0:
            continue

        position_bytes = positions.tobytes()
        binary_blob, position_offset = _append_aligned(binary_blob, position_bytes, 4)
        position_view = len(buffer_views)
        buffer_views.append(
            {
                "buffer": 0,
                "byteOffset": position_offset,
                "byteLength": len(position_bytes),
                "target": _ARRAY_BUFFER,
            }
        )
        position_accessor = len(accessors)
        accessors.append(
            {
                "bufferView": position_view,
                "byteOffset": 0,
                "componentType": _FLOAT,
                "count": len(positions),
                "type": "VEC3",
                "min": positions.min(axis=0).tolist(),
                "max": positions.max(axis=0).tolist(),
            }
        )

        normal_bytes = normals.tobytes()
        binary_blob, normal_offset = _append_aligned(binary_blob, normal_bytes, 4)
        normal_view = len(buffer_views)
        buffer_views.append(
            {
                "buffer": 0,
                "byteOffset": normal_offset,
                "byteLength": len(normal_bytes),
                "target": _ARRAY_BUFFER,
            }
        )
        normal_accessor = len(accessors)
        accessors.append(
            {
                "bufferView": normal_view,
                "byteOffset": 0,
                "componentType": _FLOAT,
                "count": len(normals),
                "type": "VEC3",
            }
        )

        feature_id_accessor = None
        if with_metadata:
            feature_ids = np.asarray(per_class_feature_ids[style_key], dtype=np.uint32)
            feature_id_bytes = feature_ids.tobytes()
            binary_blob, feature_id_offset = _append_aligned(binary_blob, feature_id_bytes, 4)
            feature_id_view = len(buffer_views)
            buffer_views.append(
                {
                    "buffer": 0,
                    "byteOffset": feature_id_offset,
                    "byteLength": len(feature_id_bytes),
                    "target": _ARRAY_BUFFER,
                }
            )
            feature_id_accessor = len(accessors)
            accessors.append(
                {
                    "bufferView": feature_id_view,
                    "byteOffset": 0,
                    "componentType": _UNSIGNED_INT,
                    "count": len(feature_ids),
                    "type": "SCALAR",
                    "min": [int(feature_ids.min())],
                    "max": [int(feature_ids.max())],
                }
            )

        index_bytes = indices.tobytes()
        binary_blob, index_offset = _append_aligned(binary_blob, index_bytes, 4)
        index_view = len(buffer_views)
        buffer_views.append(
            {
                "buffer": 0,
                "byteOffset": index_offset,
                "byteLength": len(index_bytes),
                "target": _ELEMENT_ARRAY_BUFFER,
            }
        )
        index_accessor = len(accessors)
        accessors.append(
            {
                "bufferView": index_view,
                "byteOffset": 0,
                "componentType": _UNSIGNED_INT,
                "count": len(indices),
                "type": "SCALAR",
                "min": [int(indices.min())],
                "max": [int(indices.max())],
            }
        )

        style = _style_for_class(style_key, class_styles)
        material_index = len(materials)
        materials.append(
            {
                "name": style.name,
                "doubleSided": True,
                "pbrMetallicRoughness": {
                    "baseColorFactor": list(style.base_color_factor),
                    "metallicFactor": 0.0,
                    "roughnessFactor": 1.0,
                },
            }
        )
        primitive: dict[str, Any] = {
            "attributes": {
                "POSITION": position_accessor,
                "NORMAL": normal_accessor,
            },
            "indices": index_accessor,
            "material": material_index,
        }
        if with_metadata and feature_id_accessor is not None:
            primitive["attributes"]["_FEATURE_ID_0"] = feature_id_accessor
            primitive["extensions"] = {
                "EXT_mesh_features": {
                    "featureIds": [
                        {
                            "featureCount": len(feature_properties),
                            "attribute": 0,
                            "propertyTable": 0,
                        }
                    ]
                }
            }
        primitives.append(primitive)

    gltf_json: dict[str, Any] = {
        "asset": {"version": "2.0", "generator": "gpkg-tiler"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [{"name": output_path.stem, "primitives": primitives}],
        "materials": materials,
        "accessors": accessors,
        "bufferViews": buffer_views,
        "buffers": [{"byteLength": len(binary_blob)}],
    }
    if with_metadata and feature_properties:
        property_keys = sorted({key for props in feature_properties for key in props.keys()})
        schema_properties: dict[str, dict[str, str]] = {}
        property_table_properties: dict[str, dict[str, Any]] = {}
        for key in property_keys:
            encoded_values = [props.get(key, "").encode("utf-8") for props in feature_properties]
            values_blob = b"".join(encoded_values)
            offsets = [0]
            cursor = 0
            for value in encoded_values:
                cursor += len(value)
                offsets.append(cursor)
            offsets_blob = struct.pack(f"<{len(offsets)}I", *offsets)

            binary_blob, values_offset = _append_aligned(binary_blob, values_blob, 1)
            values_view = len(buffer_views)
            buffer_views.append(
                {
                    "buffer": 0,
                    "byteOffset": values_offset,
                    "byteLength": len(values_blob),
                }
            )

            binary_blob, offsets_offset = _append_aligned(binary_blob, offsets_blob, 4)
            offsets_view = len(buffer_views)
            buffer_views.append(
                {
                    "buffer": 0,
                    "byteOffset": offsets_offset,
                    "byteLength": len(offsets_blob),
                }
            )

            schema_properties[key] = {"type": "STRING"}
            property_table_properties[key] = {
                "values": values_view,
                "stringOffsets": offsets_view,
                "stringOffsetType": "UINT32",
            }

        gltf_json["buffers"][0]["byteLength"] = len(binary_blob)
        gltf_json["extensionsUsed"] = ["EXT_mesh_features", "EXT_structural_metadata"]
        gltf_json["extensions"] = {
            "EXT_structural_metadata": {
                "schema": {
                    "id": "surface_metadata_schema",
                    "classes": {
                        "surface": {
                            "properties": schema_properties,
                        }
                    },
                },
                "propertyTables": [
                    {
                        "name": "surface_properties",
                        "class": "surface",
                        "count": len(feature_properties),
                        "properties": property_table_properties,
                    }
                ],
            }
        }
    _write_glb(output_path, gltf_json, binary_blob)


def _export_tile(
    tile_key: tuple[int, int],
    surfaces: list[SurfaceFeature],
    output_dir: Path,
    to_ecef: Transformer,
    ecef_to_wgs84: Transformer,
    z_offset: float,
    with_metadata: bool,
    class_styles: dict[str, MaterialStyle],
) -> TileInfo | None:
    triangles_input_crs: list[np.ndarray] = []
    triangle_style_keys: list[str] = []
    triangle_feature_ids: list[int] = []
    feature_properties: list[dict[str, str]] = []

    for feature_id, surface in enumerate(surfaces):
        feature_properties.append(surface.properties)
        for triangle in _triangulate_surface(surface):
            triangles_input_crs.append(triangle)
            triangle_style_keys.append(_style_key_for_surface(surface, class_styles))
            triangle_feature_ids.append(feature_id)

    if not triangles_input_crs:
        return None

    points_input = np.vstack(triangles_input_crs)
    points_ecef = _points_to_ecef(points_input, to_ecef, z_offset=z_offset)
    origin_ecef = points_ecef.mean(axis=0)
    lon, lat, _height = ecef_to_wgs84.transform(origin_ecef[0], origin_ecef[1], origin_ecef[2])

    points_enu = _ecef_to_enu_batch(points_ecef, origin_ecef, lon, lat)
    enu_min = points_enu.min(axis=0)
    enu_max = points_enu.max(axis=0)
    region = _bounding_region(enu_min, enu_max, origin_ecef, lon, lat, ecef_to_wgs84)

    points_y_up = np.column_stack([points_enu[:, 0], points_enu[:, 2], -points_enu[:, 1]]).astype(np.float32)
    triangles_y_up = [points_y_up[index : index + 3] for index in range(0, len(points_y_up), 3)]

    relative_uri = f"tiles/tile_{tile_key[0]}_{tile_key[1]}.glb"
    _build_glb_for_tile(
        triangles_y_up,
        triangle_style_keys,
        triangle_feature_ids,
        feature_properties,
        output_dir / relative_uri,
        with_metadata,
        class_styles,
    )

    return TileInfo(
        key=tile_key,
        uri=relative_uri,
        region=region,
        transform=_enu_to_ecef_transform(lon, lat, origin_ecef),
        feature_count=len(surfaces),
    )


def _group_surfaces_into_tiles(
    surfaces: list[SurfaceFeature],
    tile_size: float,
) -> dict[tuple[int, int], list[SurfaceFeature]]:
    grouped_by_feature: dict[str, list[SurfaceFeature]] = defaultdict(list)
    for surface in surfaces:
        grouped_by_feature[surface.group_id].append(surface)

    tiles: dict[tuple[int, int], list[SurfaceFeature]] = defaultdict(list)
    for feature_surfaces in grouped_by_feature.values():
        centroid = np.mean(
            np.vstack([surface.centroid_xy for surface in feature_surfaces]),
            axis=0,
        )
        tile_key = (
            math.floor(float(centroid[0]) / tile_size),
            math.floor(float(centroid[1]) / tile_size),
        )
        tiles[tile_key].extend(feature_surfaces)
    return dict(tiles)


def _normalize_group_elevation_to_zero(
    surfaces: list[SurfaceFeature],
) -> list[SurfaceFeature]:
    grouped: dict[str, list[SurfaceFeature]] = defaultdict(list)
    for surface in surfaces:
        grouped[surface.group_id].append(surface)

    normalized: list[SurfaceFeature] = []
    for group_surfaces in grouped.values():
        min_z = min(
            float(coords[:, 2].min())
            for surface in group_surfaces
            for coords in [surface.exterior, *surface.holes]
        )
        for surface in group_surfaces:
            normalized_surface = deepcopy(surface)
            normalized_surface.exterior = normalized_surface.exterior.copy()
            normalized_surface.exterior[:, 2] -= min_z
            normalized_surface.holes = [hole.copy() for hole in normalized_surface.holes]
            for hole in normalized_surface.holes:
                hole[:, 2] -= min_z
            normalized.append(normalized_surface)
    return normalized


def export_gpkg_to_3d_tiles(
    gpkg_path: Path,
    output_dir: Path,
    *,
    layer: str | None = None,
    building_id_field: str | None = None,
    class_field: str | None = None,
    default_class: str = "default",
    tile_size: float = 250.0,
    root_geometric_error: float | None = None,
    no_elevation: bool = False,
    with_metadata: bool = False,
    class_colors: dict[str, str] | None = None,
    overwrite: bool = False,
) -> Path:
    if tile_size <= 0:
        raise ValueError("tile_size must be > 0")

    gpkg_path = gpkg_path.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    if not gpkg_path.exists():
        raise FileNotFoundError(gpkg_path)

    if output_dir.exists() and any(output_dir.iterdir()) and not overwrite:
        raise FileExistsError(f"Output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    surfaces, crs = read_surfaces(
        gpkg_path,
        layer=layer,
        building_id_field=building_id_field,
        class_field=class_field,
        default_class=default_class,
    )
    if no_elevation:
        surfaces = _normalize_group_elevation_to_zero(surfaces)
    tiles = _group_surfaces_into_tiles(surfaces, tile_size)
    if not tiles:
        raise ValueError("No spatial tiles were generated.")

    to_ecef, ecef_to_wgs84 = _make_transformers(crs)
    z_offset = 0.0 if no_elevation else _source_z_to_ellipsoidal_offset(crs)
    class_styles = _build_class_styles(class_colors)
    tile_infos: list[TileInfo] = []
    for tile_key in sorted(tiles.keys()):
        tile_info = _export_tile(
            tile_key,
            tiles[tile_key],
            output_dir,
            to_ecef,
            ecef_to_wgs84,
            z_offset,
            with_metadata,
            class_styles,
        )
        if tile_info is not None:
            tile_infos.append(tile_info)

    if not tile_infos:
        raise ValueError("No tile content was exported.")

    west = min(tile.region[0] for tile in tile_infos)
    south = min(tile.region[1] for tile in tile_infos)
    east = max(tile.region[2] for tile in tile_infos)
    north = max(tile.region[3] for tile in tile_infos)
    min_height = min(tile.region[4] for tile in tile_infos)
    max_height = max(tile.region[5] for tile in tile_infos)
    geometric_error = float(root_geometric_error if root_geometric_error is not None else tile_size)

    tileset = {
        "asset": {"version": "1.1"},
        "geometricError": geometric_error,
        "root": {
            "boundingVolume": {
                "region": [west, south, east, north, min_height, max_height],
            },
            "geometricError": geometric_error,
            "refine": "REPLACE",
            "children": [
                {
                    "boundingVolume": {"region": tile.region},
                    "geometricError": 0.0,
                    "transform": tile.transform,
                    "content": {"uri": tile.uri},
                }
                for tile in tile_infos
            ],
        },
    }

    tileset_path = output_dir / "tileset.json"
    tileset_path.write_text(json.dumps(tileset, indent=2), encoding="utf-8")
    return tileset_path
