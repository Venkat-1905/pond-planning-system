import numpy as np
import pytest
from backend.core.kml_parser import parse_kml_or_kmz, MetricProjector
from backend.core.dem_interpolator import DEMGrid, generate_dem_from_contours
from backend.core.hydrology import HydrologyEngine

SAMPLE_KML_PATH = "/home/venkat/Desktop/pond/contours_1m.kml"

def test_synthetic_hydrology():
    # Construct a synthetic V-shaped valley draining south to (4, 2)
    elev = np.array([
        [10.0, 8.0, 6.0, 8.0, 10.0],
        [9.0,  7.0, 5.0, 7.0, 9.0],
        [8.0,  6.0, 4.0, 6.0, 8.0],
        [7.0,  5.0, 3.0, 5.0, 7.0],
        [6.0,  4.0, 2.0, 4.0, 6.0]
    ], dtype=float)

    proj = MetricProjector(81.29, 21.25)
    dem = DEMGrid(
        elevation_grid=elev,
        x_coords=np.linspace(0, 40, 5),
        y_coords=np.linspace(40, 0, 5),
        cell_size=10.0,
        projector=proj,
        min_elev=2.0,
        max_elev=10.0
    )

    hydro = HydrologyEngine(dem)
    # The outlet at (4, 2) should accumulate all or most upstream cells
    assert hydro.flow_acc[4, 2] >= 10

    mask, area = hydro.delineate_catchment(4, 2)
    assert mask[4, 2] == True
    assert mask[0, 2] == True  # Ridge channel should flow down
    assert area == np.sum(mask) * 100.0

def test_sample_kml_hydrology():
    with open(SAMPLE_KML_PATH, "rb") as f:
        parsed = parse_kml_or_kmz(f.read(), "contours_1m.kml")

    dem = generate_dem_from_contours(parsed)
    assert dem.elevation.shape[0] > 100
    assert dem.elevation.shape[1] > 100

    hydro = HydrologyEngine(dem)
    assert np.all(hydro.flow_acc >= 1)
    max_acc = np.max(hydro.flow_acc)
    assert max_acc > 1000

    # Delineate from maximum accumulation cell
    best_r, best_c = np.unravel_index(np.argmax(hydro.flow_acc), hydro.flow_acc.shape)
    lon, lat = dem.grid_to_geo(best_r, best_c)
    mask, area = hydro.delineate_catchment(best_r, best_c)
    geojson = hydro.catchment_to_geojson(mask, lat, lon, area)

    assert area > 100000.0  # > 10 ha
    assert geojson["type"] == "Feature"
    assert geojson["geometry"]["type"] in ["Polygon", "MultiPolygon"]
