import os
import pytest
from fastapi.testclient import TestClient
from backend.app import app

client = TestClient(app)
SAMPLE_KML_PATH = "/home/venkat/Desktop/pond/contours_1m.kml"

def test_health_endpoint():
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "version" in data

def test_analyze_contour_api():
    assert os.path.exists(SAMPLE_KML_PATH)
    with open(SAMPLE_KML_PATH, "rb") as f:
        resp = client.post(
            "/api/v1/analyzeContour",
            files={"contour_map": ("contours_1m.kml", f, "application/vnd.google-earth.kml+xml")}
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["contour_count"] > 1000
    assert len(data["recommended_pond_sites"]) >= 1
    assert data["bounds"]["area_km2"] > 0
    assert data["elevation_stats"]["relief_m"] > 0

def test_process_all_with_contour_map():
    with open(SAMPLE_KML_PATH, "rb") as f:
        resp = client.post(
            "/processAll",
            files={"contour_map": ("contours_1m.kml", f, "application/vnd.google-earth.kml+xml")},
            data={"land_cover": "agricultural"}
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "terrain_analysis" in data
    assert "pond_design" in data
    assert "catchment_geojson" in data

def test_find_catchment_auto():
    with open(SAMPLE_KML_PATH, "rb") as f:
        resp = client.post(
            "/api/v1/findCatchment",
            files={"file": ("contours_1m.kml", f, "application/vnd.google-earth.kml+xml")},
            data={"land_cover": "agricultural"}
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["catchment_area"]["hectares"] > 10.0
    assert data["annual_runoff_volume_m3"] > 0
    assert data["pond_design"]["recommended_depth_m"] >= 2.0
    assert data["catchment_geojson"]["geometry"]["type"] in ["Polygon", "MultiPolygon"]

def test_find_catchment_manual_coordinates():
    with open(SAMPLE_KML_PATH, "rb") as f:
        resp = client.post(
            "/api/v1/findCatchment",
            files={"file": ("contours_1m.kml", f, "application/vnd.google-earth.kml+xml")},
            data={
                "pond_lat": "21.2442",
                "pond_lon": "81.2882",
                "land_cover": "forest",
                "storage_efficiency": "0.75"
            }
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["hydrology"]["land_cover"] == "forest"
    assert data["hydrology"]["runoff_coefficient"] == 0.30

def test_pond_analyze_direct():
    resp = client.post(
        "/api/v1/pond/analyze",
        json={
            "pond_lat": 21.2442,
            "pond_lon": 81.2882,
            "catchment_area_m2": 500000.0,
            "runoff_coeff": 0.45,
            "rainfall_mm": 1200.0,
            "land_cover": "agricultural"
        }
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    # Q = (0.45 * 1200 * 500000) / 1000 = 270,000 m3
    assert data["annual_runoff_volume_m3"] == 270000.0

def test_input_validation_errors():
    # Negative rainfall
    resp = client.post(
        "/api/v1/pond/analyze",
        json={
            "pond_lat": 21.2442,
            "pond_lon": 81.2882,
            "catchment_area_m2": 500000.0,
            "rainfall_mm": -50.0
        }
    )
    assert resp.status_code == 422  # Pydantic unprocessable entity

    # Runoff coeff out of range
    resp2 = client.post(
        "/api/v1/pond/analyze",
        json={
            "pond_lat": 21.2442,
            "pond_lon": 81.2882,
            "catchment_area_m2": 500000.0,
            "runoff_coeff": 1.5
        }
    )
    assert resp2.status_code == 422
