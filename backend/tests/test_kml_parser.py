import os
import pytest
from backend.core.kml_parser import parse_kml_or_kmz, MetricProjector

SAMPLE_KML_PATH = "/home/venkat/Desktop/pond/contours_1m.kml"

def test_metric_projector():
    proj = MetricProjector(center_lon=81.30, center_lat=21.25)
    x, y = proj.to_metric(81.30, 21.25)
    assert abs(x) < 1e-3
    assert abs(y) < 1e-3

    lon, lat = proj.to_geo(x, y)
    assert abs(lon - 81.30) < 1e-6
    assert abs(lat - 21.25) < 1e-6

def test_parse_sample_kml():
    assert os.path.exists(SAMPLE_KML_PATH), "Sample KML must exist"
    with open(SAMPLE_KML_PATH, "rb") as f:
        parsed = parse_kml_or_kmz(f.read(), "contours_1m.kml")

    assert len(parsed.contours) > 1000
    assert 265.0 <= parsed.min_elev <= 270.0
    assert 295.0 <= parsed.max_elev <= 300.0
    assert parsed.relief > 20.0
    assert 81.28 <= parsed.min_lon <= parsed.max_lon <= 81.32
    assert 21.23 <= parsed.min_lat <= parsed.max_lat <= 21.27

def test_kml_geojson_generation():
    with open(SAMPLE_KML_PATH, "rb") as f:
        parsed = parse_kml_or_kmz(f.read(), "contours_1m.kml")

    geo = parsed.to_geojson(max_features=50)
    assert geo["type"] == "FeatureCollection"
    assert len(geo["features"]) == 50
    assert "elevation" in geo["features"][0]["properties"]
    assert geo["features"][0]["geometry"]["type"] == "LineString"

def test_invalid_kml():
    with pytest.raises(ValueError):
        parse_kml_or_kmz(b"<xml>invalid</xml>", "test.kml")
