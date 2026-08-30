"""
Generalized KML and KMZ parser for terrain contour maps.
Extracts isoline geometries, elevation values, computes spatial extents,
and performs dynamic metric projections without hardcoding.
"""

import io
import math
import re
import zipfile
import xml.etree.ElementTree as ET
from typing import List, Tuple, Dict, Any, Optional


class ContourLine:
    def __init__(self, elevation: float, coordinates: List[Tuple[float, float]], feature_id: Optional[str] = None):
        self.elevation = float(elevation)
        self.coordinates = coordinates  # [(lon, lat), ...]
        self.feature_id = feature_id


class MetricProjector:
    """
    Dynamic local projection transforming WGS84 (lon, lat) to local Cartesian metric (x, y) in meters.
    Centered at the bounding box centroid.
    """
    def __init__(self, center_lon: float, center_lat: float):
        self.center_lon = center_lon
        self.center_lat = center_lat
        self.r_earth = 6371000.0  # Mean earth radius in meters
        self.lat_rad = math.radians(center_lat)
        self.cos_lat = math.cos(self.lat_rad)
        self.m_per_deg_lat = (math.pi / 180.0) * self.r_earth
        self.m_per_deg_lon = (math.pi / 180.0) * self.r_earth * self.cos_lat

    def to_metric(self, lon: float, lat: float) -> Tuple[float, float]:
        x = (lon - self.center_lon) * self.m_per_deg_lon
        y = (lat - self.center_lat) * self.m_per_deg_lat
        return x, y

    def to_geo(self, x: float, y: float) -> Tuple[float, float]:
        lon = self.center_lon + (x / self.m_per_deg_lon)
        lat = self.center_lat + (y / self.m_per_deg_lat)
        return lon, lat


class ParsedContourMap:
    def __init__(self, contours: List[ContourLine], boundary_polygon: Optional[List[Tuple[float, float]]] = None):
        if not contours:
            raise ValueError("No valid contour lines found in the input file.")
        self.contours = contours
        self.boundary_polygon = boundary_polygon
        self._calculate_bounds()

    def _calculate_bounds(self):
        all_lons = []
        all_lats = []
        all_elevations = []
        total_pts = 0

        for c in self.contours:
            all_elevations.append(c.elevation)
            for lon, lat in c.coordinates:
                all_lons.append(lon)
                all_lats.append(lat)
                total_pts += 1

        self.min_lon = min(all_lons)
        self.max_lon = max(all_lons)
        self.min_lat = min(all_lats)
        self.max_lat = max(all_lats)
        self.center_lon = (self.min_lon + self.max_lon) / 2.0
        self.center_lat = (self.min_lat + self.max_lat) / 2.0

        self.min_elev = min(all_elevations)
        self.max_elev = max(all_elevations)
        self.mean_elev = sum(all_elevations) / len(all_elevations)
        self.relief = self.max_elev - self.min_elev

        self.total_vertices = total_pts
        self.projector = MetricProjector(self.center_lon, self.center_lat)

        x_min, y_min = self.projector.to_metric(self.min_lon, self.min_lat)
        x_max, y_max = self.projector.to_metric(self.max_lon, self.max_lat)
        self.width_m = x_max - x_min
        self.height_m = y_max - y_min
        self.area_km2 = (self.width_m * self.height_m) / 1e6

    def get_points_cloud(self) -> Tuple[List[Tuple[float, float]], List[float]]:
        points_xy = []
        values_z = []
        for c in self.contours:
            for lon, lat in c.coordinates:
                x, y = self.projector.to_metric(lon, lat)
                points_xy.append((x, y))
                values_z.append(c.elevation)
        return points_xy, values_z

    def to_geojson(self, max_features: Optional[int] = None) -> Dict[str, Any]:
        features = []
        contours_to_use = self.contours[:max_features] if max_features else self.contours
        for idx, c in enumerate(contours_to_use):
            features.append({
                "type": "Feature",
                "properties": {
                    "id": c.feature_id or str(idx),
                    "elevation": c.elevation
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[lon, lat] for lon, lat in c.coordinates]
                }
            })
        return {
            "type": "FeatureCollection",
            "features": features
        }


def parse_kml_or_kmz(file_content: bytes, filename: str = "") -> ParsedContourMap:
    """
    Parses a KML or KMZ file bytes and extracts all contour lines with elevations.
    """
    kml_bytes = None

    if filename.lower().endswith(".kmz") or file_content.startswith(b"PK"):
        try:
            with zipfile.ZipFile(io.BytesIO(file_content)) as z:
                kml_files = [f for f in z.namelist() if f.lower().endswith(".kml")]
                if not kml_files:
                    raise ValueError("KMZ archive contains no .kml files.")
                target = "doc.kml" if "doc.kml" in kml_files else kml_files[0]
                kml_bytes = z.read(target)
        except zipfile.BadZipFile:
            raise ValueError("Invalid KMZ archive file format.")
    else:
        kml_bytes = file_content

    return _parse_kml_xml(kml_bytes)


def _parse_kml_xml(kml_bytes: bytes) -> ParsedContourMap:
    try:
        root = ET.fromstring(kml_bytes)
    except ET.ParseError as e:
        raise ValueError(f"Failed to parse KML XML: {e}")

    contours: List[ContourLine] = []
    boundary_polygon: Optional[List[Tuple[float, float]]] = None

    # Strip XML namespaces for flexible tag matching
    for elem in root.iter():
        if "}" in elem.tag:
            elem.tag = elem.tag.split("}", 1)[1]

    for placemark in root.iter("Placemark"):
        # Check for Polygon boundary
        poly_el = placemark.find(".//Polygon/outerBoundaryIs/LinearRing/coordinates")
        if poly_el is not None and poly_el.text:
            coords, _ = _parse_coordinates_string(poly_el.text)
            if len(coords) >= 3:
                boundary_polygon = coords

        # Only process LineString geometries for contour lines
        linestring_elements = placemark.findall(".//LineString/coordinates")
        if not linestring_elements:
            continue

        elev = _extract_elevation_from_placemark(placemark)
        feature_id = _extract_id_from_placemark(placemark)

        for ce in linestring_elements:
            if ce.text:
                coords, fallback_elev = _parse_coordinates_string(ce.text)
                final_elev = elev if elev is not None else fallback_elev
                if final_elev is not None and len(coords) >= 2:
                    contours.append(ContourLine(final_elev, coords, feature_id))

    if not contours:
        raise ValueError("No contour line strings with valid elevation values found in KML.")

    return ParsedContourMap(contours, boundary_polygon)


def _extract_elevation_from_placemark(placemark: ET.Element) -> Optional[float]:
    # 1. Try <name> (common pattern: '277.0', '280.0', '280m', etc.)
    name_el = placemark.find("name")
    if name_el is not None and name_el.text:
        text = name_el.text.strip()
        # Strictly match numeric elevation pattern (e.g. 277.0, 280, 152.4)
        if re.match(r"^[-+]?\d+(?:\.\d+)?(?:\s*(?:m|meters|ft))?$", text, re.IGNORECASE):
            num_match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
            if num_match:
                try:
                    return float(num_match.group(0))
                except ValueError:
                    pass

    # 2. Try <ExtendedData><SimpleData>
    for simple_data in placemark.findall(".//SimpleData"):
        name_attr = simple_data.attrib.get("name", "").lower()
        if any(k in name_attr for k in ["elev", "contour", "height", "z", "val"]):
            if simple_data.text:
                try:
                    return float(simple_data.text.strip())
                except ValueError:
                    pass

    # 3. Try <description>
    desc_el = placemark.find("description")
    if desc_el is not None and desc_el.text:
        match = re.search(r"(?:elevation|contour|elev|height)[:\s=]+([-+]?\d+(?:\.\d+)?)", desc_el.text, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass

    return None


def _extract_id_from_placemark(placemark: ET.Element) -> Optional[str]:
    if "id" in placemark.attrib:
        return placemark.attrib["id"]
    for sd in placemark.findall(".//SimpleData"):
        if sd.attrib.get("name", "").upper() == "ID" and sd.text:
            return sd.text.strip()
    return None


def _parse_coordinates_string(raw_str: str) -> Tuple[List[Tuple[float, float]], Optional[float]]:
    coords = []
    elev_candidates = []
    tokens = raw_str.strip().split()

    for token in tokens:
        parts = token.split(",")
        if len(parts) >= 2:
            try:
                lon = float(parts[0])
                lat = float(parts[1])
                coords.append((lon, lat))
                if len(parts) >= 3:
                    z = float(parts[2])
                    if z != 0.0:
                        elev_candidates.append(z)
            except ValueError:
                continue

    fallback_elev = elev_candidates[0] if elev_candidates else None
    return coords, fallback_elev
