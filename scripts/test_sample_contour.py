#!/usr/bin/env python3
# CLI Demonstration Script for Village Pond Planning System.

import os
import sys
import json
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.core.kml_parser import parse_kml_or_kmz
from backend.core.dem_interpolator import generate_dem_from_contours
from backend.core.hydrology import HydrologyEngine
from backend.core.pond_optimizer import PondOptimizer
from backend.core.schemas import LandCoverType

def main():
    kml_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../contours_1m.kml"))
    if not os.path.exists(kml_path):
        print(f"Error: Sample KML file not found at {kml_path}")
        sys.exit(1)

    print("=" * 80)
    print("      AI-BASED VILLAGE POND PLANNING SYSTEM - TERRAIN & CATCHMENT ENGINE")
    print("=" * 80)
    print(f"Loading input file: {kml_path}")

    t0 = time.time()
    with open(kml_path, "rb") as f:
        file_bytes = f.read()

    # 1. Parse KML
    parsed = parse_kml_or_kmz(file_bytes, "contours_1m.kml")
    t1 = time.time()
    print(f"[OK] Parsed {len(parsed.contours)} contour lines ({parsed.total_vertices:,} coordinate points) in {t1 - t0:.2f}s")
    print(f"     Spatial Extent: Longitude [{parsed.min_lon:.5f}, {parsed.max_lon:.5f}]")
    print(f"                     Latitude  [{parsed.min_lat:.5f}, {parsed.max_lat:.5f}]")
    print(f"     Ground Dimensions: {parsed.width_m:.1f}m (W) x {parsed.height_m:.1f}m (H) -> Area: {parsed.area_km2:.2f} km^2")
    print(f"     Elevation Profile: Min = {parsed.min_elev:.1f}m, Max = {parsed.max_elev:.1f}m, Relief = {parsed.relief:.1f}m")

    # 2. DEM Interpolation & Slope
    dem = generate_dem_from_contours(parsed)
    t2 = time.time()
    print()
    print(f"[OK] DEM Reconstructed: Grid size {dem.nrows} x {dem.ncols} cells ({dem.cell_size:.1f}m resolution) in {t2 - t1:.2f}s")
    print(f"     Mean Ground Slope: {dem.mean_slope_pct:.2f}% | Max Slope: {dem.max_slope_pct:.2f}%")
    print(f"     Pond Suitable Flat Land (Slope < 5%): {dem.flat_area_pct:.1f}% of total landscape")

    # 3. Hydrology Engine (D8 & Accumulation)
    hydro = HydrologyEngine(dem)
    t3 = time.time()
    print()
    print(f"[OK] Hydrology Modeled: D8 Flow Direction & Upstream Accumulation in {t3 - t2:.2f}s")
    print(f"     Max Stream Accumulation: {hydro.flow_acc.max():,} cells (~{hydro.flow_acc.max() * hydro.cell_area_m2 / 1e6:.2f} km^2 contributing)")

    # 4. Pond Candidate Discovery
    optimizer = PondOptimizer(dem, hydro)
    candidates = optimizer.find_candidate_pond_sites(top_k=3)
    print()
    print("-" * 80)
    print("                   TOP RECOMMENDED POND LOCATIONS")
    print("-" * 80)
    for c in candidates:
        print(f"  [Rank {c.rank}] Suitability Score: {c.suitability_score}/100")
        print(f"         Location: Lat {c.lat:.6f} N, Lon {c.lon:.6f} E (Elev: {c.elevation_m}m, Slope: {c.slope_pct}%)")
        print(f"         Estimated Catchment Area: {c.estimated_catchment_m2 / 10000:.1f} hectares ({c.estimated_catchment_m2 / 1e6:.3f} km^2)")
        print(f"         Recommendation: {c.recommendation}")
        for r in c.reasons:
            print(f"           - {r}")
        print()

    # 5. Delineate Catchment for Rank 1
    best = candidates[0]
    best_r, best_c = dem.geo_to_grid(best.lon, best.lat)
    t4 = time.time()
    c_mask, c_area_m2 = hydro.delineate_catchment(best_r, best_c)
    geojson_data = hydro.catchment_to_geojson(c_mask, best.lat, best.lon, c_area_m2)
    t5 = time.time()

    print("-" * 80)
    print("          DELINEATED CATCHMENT & SIZING FOR PRIMARY POND SITE (RANK 1)")
    print("-" * 80)
    print(f"  Outlet Coordinates: Lat {best.lat:.6f} N, Lon {best.lon:.6f} E")
    print(f"  Delineated Catchment Area: {c_area_m2:,.1f} m^2  ({c_area_m2 / 10000:.2f} hectares / {c_area_m2 / 1e6:.3f} km^2)")
    print(f"  Delineation Compute Time: {t5 - t4:.3f} seconds")

    # 6. Sizing & Hydrological Estimation
    design, hydro_p, runoff_vol = PondOptimizer.calculate_pond_design(
        catchment_area_m2=c_area_m2,
        slope_pct=best.slope_pct,
        land_cover=LandCoverType.AGRICULTURAL,
        lat=best.lat,
        lon=best.lon
    )

    print()
    print("  Hydrological Parameters:")
    print(f"    - Land Cover: {hydro_p.land_cover} -> Runoff Coeff C = {hydro_p.runoff_coefficient}")
    print(f"    - Annual Rainfall: {hydro_p.annual_rainfall_mm} mm ({hydro_p.rainfall_data_source})")
    print(f"    - Estimated Annual Runoff Volume: {runoff_vol:,.1f} m^3")

    print()
    print("  Recommended Pond Dimensions (Trapezoidal 2:1 Side Slope):")
    print(f"    - Target Storage Capacity: {design.target_storage_m3:,.1f} m^3")
    print(f"    - Recommended Total Depth: {design.recommended_depth_m} m (Water: {design.water_depth_m}m + Freeboard: {design.freeboard_m}m)")
    print(f"    - Top Surface Dimensions: {design.length_m} m (Length) x {design.width_m} m (Width)")
    print(f"    - Top Water Surface Area: {design.top_surface_area_m2:,.1f} m^2")
    print(f"    - Bottom Base Area: {design.bottom_base_area_m2:,.1f} m^2")
    print(f"    - Earth Excavation Volume: {design.excavation_volume_m3:,.1f} m^3")

    # Export GeoJSON
    out_geojson_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../sample_catchment_output.geojson"))
    with open(out_geojson_path, "w") as f:
        json.dump(geojson_data, f, indent=2)
    print()
    print(f"[OK] Catchment boundary polygon exported to: {out_geojson_path}")
    print("=" * 80)

if __name__ == "__main__":
    main()
