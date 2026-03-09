from __future__ import annotations

from pathlib import Path
from typing import Iterable

import geopandas as gpd
import numpy as np
from pyogrio.raw import read as raw_read
from pyproj import CRS
import shapely
from shapely.geometry import MultiPolygon, Polygon

from .models import SurfaceFeature

_CLASS_ALIASES: dict[str, str] = {
    "wall": "wall",
    "wallsurface": "wall",
    "roof": "roof",
    "roofsurface": "roof",
    "window": "window",
    "windowsurface": "window",
    "door": "door",
    "doorsurface": "door",
    "ground": "ground",
    "groundsurface": "ground",
    "terrain": "ground",
    "tree": "tree_canopy",
    "canopy": "tree_canopy",
    "tree_canopy": "tree_canopy",
    "treecanopy": "tree_canopy",
    "trunk": "tree_trunk",
    "tree_trunk": "tree_trunk",
    "treetrunk": "tree_trunk",
}


def _resolve_column_name(columns: list[str], requested: str, label: str) -> str:
    if requested in columns:
        return requested
    lowered = {column.lower(): column for column in columns}
    resolved = lowered.get(requested.lower())
    if resolved is not None:
        return resolved
    available = ", ".join(columns)
    raise KeyError(f"Missing {label} field '{requested}'. Available columns: {available}")


def normalize_semantic_class(value: object, default_class: str = "default") -> str:
    if value is None:
        return default_class
    text = str(value).strip().lower().replace(" ", "_").replace("-", "_")
    if not text:
        return default_class
    return _CLASS_ALIASES.get(text, default_class)


def _coords3d(coords: Iterable[tuple[float, ...]]) -> np.ndarray:
    arr = np.asarray(list(coords), dtype=float)
    if arr.ndim != 2 or arr.shape[0] < 4:
        raise ValueError("Polygon ring must have at least four coordinates.")
    if arr.shape[1] == 2:
        arr = np.column_stack([arr, np.zeros((arr.shape[0],), dtype=float)])
    return arr[:, :3]


def _extract_polygons(geom: object) -> list[Polygon]:
    if geom is None:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return list(geom.geoms)
    return []


def _centroid_xy_from_exterior(exterior: np.ndarray) -> np.ndarray:
    ring_xy = exterior[:-1, :2] if len(exterior) > 1 and np.allclose(exterior[0], exterior[-1]) else exterior[:, :2]
    if len(ring_xy) == 0:
        raise ValueError("Polygon exterior is empty.")
    min_xy = ring_xy.min(axis=0)
    max_xy = ring_xy.max(axis=0)
    centroid_xy = (min_xy + max_xy) / 2.0
    if not np.isfinite(centroid_xy).all():
        raise ValueError("Polygon centroid is not finite.")
    return centroid_xy


def read_surfaces(
    gpkg_path: Path,
    *,
    layer: str | None = None,
    building_id_field: str | None = None,
    class_field: str | None = None,
    default_class: str = "default",
) -> tuple[list[SurfaceFeature], CRS]:
    available_layers = gpd.list_layers(gpkg_path)
    available_layer_names = available_layers["name"].tolist()
    if layer is not None and layer not in available_layer_names:
        available = ", ".join(available_layer_names)
        raise KeyError(f"Missing layer '{layer}'. Available layers: {available}")
    if layer is None and len(available_layer_names) > 1:
        available = ", ".join(available_layer_names)
        raise ValueError(
            f"GeoPackage contains multiple layers. Please provide --layer. Available layers: {available}"
        )

    metadata, _feature_ids, wkb, field_arrays = raw_read(str(gpkg_path), layer=layer)
    field_names = metadata["fields"].tolist()
    crs_value = metadata.get("crs")
    if crs_value is None:
        raise ValueError(f"No CRS found in {gpkg_path}")

    columns = [*field_names, "geometry"]
    resolved_building_id_field = (
        _resolve_column_name(columns, building_id_field, "building id")
        if building_id_field is not None
        else None
    )
    resolved_class_field = (
        _resolve_column_name(columns, class_field, "class")
        if class_field is not None
        else None
    )
    field_name_to_index = {name: index for index, name in enumerate(field_names)}
    geometries = shapely.from_wkb(wkb, on_invalid="ignore")

    surfaces: list[SurfaceFeature] = []
    for row_index, geom in enumerate(geometries):
        if geom is None or geom.is_empty:
            continue

        group_id = (
            str(field_arrays[field_name_to_index[resolved_building_id_field]][row_index])
            if resolved_building_id_field is not None
            else f"feature_{row_index}"
        )
        source_class = (
            None
            if resolved_class_field is None or field_arrays[field_name_to_index[resolved_class_field]][row_index] is None
            else str(field_arrays[field_name_to_index[resolved_class_field]][row_index])
        )
        semantic_class = normalize_semantic_class(
            source_class,
            default_class=default_class,
        )
        properties = {
            field_name: "" if field_arrays[field_name_to_index[field_name]][row_index] is None else str(field_arrays[field_name_to_index[field_name]][row_index])
            for field_name in field_names
        }
        properties["source_id"] = f"{group_id}_{row_index}"
        properties["group_id"] = group_id
        properties["semantic_class"] = semantic_class
        properties["source_class"] = source_class or ""

        for polygon_index, polygon in enumerate(_extract_polygons(geom)):
            try:
                exterior = _coords3d(polygon.exterior.coords)
                centroid_xy = _centroid_xy_from_exterior(exterior)
            except ValueError:
                continue
            if not np.isfinite(exterior).all():
                continue
            holes: list[np.ndarray] = []
            for interior in polygon.interiors:
                try:
                    hole = _coords3d(interior.coords)
                except ValueError:
                    continue
                if not np.isfinite(hole).all():
                    continue
                holes.append(hole)

            surfaces.append(
                SurfaceFeature(
                    source_id=f"{group_id}_{row_index}_{polygon_index}",
                    group_id=group_id,
                    semantic_class=semantic_class,
                    exterior=exterior,
                    holes=holes,
                    centroid_xy=centroid_xy,
                    properties={
                        **properties,
                        "source_id": f"{group_id}_{row_index}_{polygon_index}",
                    },
                    source_class=source_class,
                )
            )

    if not surfaces:
        raise ValueError(f"No polygon surfaces found in {gpkg_path}")
    return surfaces, CRS.from_user_input(crs_value)
