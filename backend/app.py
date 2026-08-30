"""
FastAPI Application for AI-Based Village Pond Planning & Catchment Analysis.
Provides REST API routes for terrain analysis, watershed catchment delineation,
and pond design sizing from KML & KMZ contour maps.
"""

import time
import os
from typing import Optional, Dict, Any
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse, Response

from backend.core.schemas import (
    LandCoverType,
    PondAnalyzeRequest,
    TerrainAnalysisResponse,
    CatchmentResponse,
    UnifiedProcessResponse,
    BoundingBox,
    ElevationStats,
    SlopeStats,
    CatchmentAreaMetrics,
    HydrologyParameters,
    PondDesignParameters
)
from backend.core.kml_parser import parse_kml_or_kmz
from backend.core.dem_interpolator import generate_dem_from_contours
from backend.core.hydrology import HydrologyEngine
from backend.core.pond_optimizer import PondOptimizer

app = FastAPI(
    title="AI-Based Village Pond Planning System API",
    description="Backend API for contour terrain analysis, watershed catchment delineation, and pond sizing.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Enable CORS for external access / frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["System"])
def health_check():
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "service": "Village Pond Planning System API",
        "version": "1.0.0"
    }


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)


@app.get("/contours_1m.kml", include_in_schema=False)
async def serve_sample_kml():
    """Serves the sample contour file for quick testing in the web UI."""
    sample_paths = [
        os.path.join(os.path.dirname(__file__), "static", "contours_1m.kml"),
        os.path.join(os.path.dirname(__file__), "..", "contours_1m.kml"),
        "/home/venkat/Desktop/pond/contours_1m.kml"
    ]
    for p in sample_paths:
        if os.path.exists(p):
            return FileResponse(p, media_type="application/vnd.google-earth.kml+xml", filename="contours_1m.kml")
    raise HTTPException(status_code=404, detail="Sample contours_1m.kml file not found.")


def _process_uploaded_kml(file_bytes: bytes, filename: str):
    try:
        parsed_map = parse_kml_or_kmz(file_bytes, filename)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse contour file: {str(e)}"
        )

    try:
        dem = generate_dem_from_contours(parsed_map)
        hydro = HydrologyEngine(dem)
        optimizer = PondOptimizer(dem, hydro)
        return parsed_map, dem, hydro, optimizer
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Terrain analysis / hydrology processing error: {str(e)}"
        )


@app.post("/analyzeContour", response_model=TerrainAnalysisResponse, tags=["Terrain Analysis"])
@app.post("/api/v1/analyzeContour", response_model=TerrainAnalysisResponse, tags=["Terrain Analysis"])
async def analyze_contour(
    file: UploadFile = File(..., description="Contour map in KML or KMZ format"),
    include_contours_geojson: bool = Query(False, description="Whether to include full contour GeoJSON (can increase payload size)")
):
    """
    Analyzes an uploaded KML/KMZ contour map:
    - Extracts contour isolines and elevation metrics.
    - Reconstructs a continuous Digital Elevation Model (DEM).
    - Computes slope gradients and flat area percentage.
    - Automatically discovers and ranks top suitable pond candidate sites.
    """
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty. Please select a valid KML/KMZ contour file.")

    parsed_map, dem, hydro, optimizer = _process_uploaded_kml(content, file.filename or "contour.kml")
    candidates = optimizer.find_candidate_pond_sites(top_k=3)

    contours_geo = parsed_map.to_geojson(max_features=500) if include_contours_geojson else None

    return TerrainAnalysisResponse(
        status="success",
        filename=file.filename or "contour.kml",
        bounds=BoundingBox(
            min_lon=round(parsed_map.min_lon, 6),
            min_lat=round(parsed_map.min_lat, 6),
            max_lon=round(parsed_map.max_lon, 6),
            max_lat=round(parsed_map.max_lat, 6),
            center_lat=round(parsed_map.center_lat, 6),
            center_lon=round(parsed_map.center_lon, 6),
            width_km=round(parsed_map.width_m / 1000.0, 3),
            height_km=round(parsed_map.height_m / 1000.0, 3),
            area_km2=round(parsed_map.area_km2, 3)
        ),
        elevation_stats=ElevationStats(
            min_m=round(dem.min_elev, 2),
            max_m=round(dem.max_elev, 2),
            mean_m=round(dem.mean_elev, 2),
            relief_m=round(dem.relief, 2)
        ),
        slope_stats=SlopeStats(
            min_pct=round(dem.min_slope_pct, 2),
            max_pct=round(dem.max_slope_pct, 2),
            mean_pct=round(dem.mean_slope_pct, 2),
            flat_area_pct=round(dem.flat_area_pct, 2)
        ),
        contour_count=len(parsed_map.contours),
        total_vertices=parsed_map.total_vertices,
        recommended_pond_sites=candidates,
        contours_geojson=contours_geo
    )


@app.post("/findCatchment", response_model=CatchmentResponse, tags=["Catchment & Hydrology"])
@app.post("/api/v1/findCatchment", response_model=CatchmentResponse, tags=["Catchment & Hydrology"])
async def find_catchment(
    file: UploadFile = File(..., description="Contour map in KML or KMZ format"),
    pond_lat: Optional[float] = Form(None, description="Proposed pond latitude (leave empty for auto-detection)"),
    pond_lon: Optional[float] = Form(None, description="Proposed pond longitude (leave empty for auto-detection)"),
    land_cover: LandCoverType = Form(LandCoverType.AGRICULTURAL, description="Dominant catchment land cover type"),
    runoff_coeff: Optional[float] = Form(None, description="Runoff coefficient override (0.1 to 0.9)"),
    rainfall_mm: Optional[float] = Form(None, description="Annual rainfall in mm override"),
    storage_efficiency: float = Form(0.70, description="Storage efficiency ratio (0.1 to 1.0)")
):
    """
    Delineates the upstream catchment watershed and calculates pond design:
    - If pond_lat and pond_lon are provided, uses specified coordinates.
    - If omitted, auto-detects the optimal pond site with highest flow accumulation.
    - Traces upstream reverse D8 flow pathways to isolate contributing catchment.
    - Applies Rational Method to estimate annual runoff and recommended pond dimensions.
    """
    if runoff_coeff is not None and not (0.1 <= runoff_coeff <= 0.9):
        raise HTTPException(status_code=400, detail="Runoff coefficient C must be between 0.1 and 0.9")
    if rainfall_mm is not None and rainfall_mm <= 0:
        raise HTTPException(status_code=400, detail="Rainfall depth R must be strictly positive")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty. Please select a valid KML/KMZ contour file.")

    parsed_map, dem, hydro, optimizer = _process_uploaded_kml(content, file.filename or "contour.kml")

    # Determine outlet location
    if pond_lat is not None and pond_lon is not None:
        target_lat, target_lon = float(pond_lat), float(pond_lon)
        target_r, target_c = dem.geo_to_grid(target_lon, target_lat)
        selection_mode = "Manual coordinate selection"
    else:
        candidates = optimizer.find_candidate_pond_sites(top_k=1)
        if not candidates:
            raise HTTPException(status_code=404, detail="No suitable pond candidate could be identified.")
        best = candidates[0]
        target_lat, target_lon = best.lat, best.lon
        target_r, target_c = dem.geo_to_grid(target_lon, target_lat)
        selection_mode = "Auto-detected optimal site (Rank 1)"

    outlet_elev = round(dem.get_elevation_at(target_r, target_c), 2)
    outlet_slope = round(dem.get_slope_at(target_r, target_c), 2)

    # Delineate catchment
    c_mask, c_area_m2 = hydro.delineate_catchment(target_r, target_c)
    catchment_geo = hydro.catchment_to_geojson(c_mask, target_lat, target_lon, c_area_m2)

    # Calculate pond sizing & runoff
    pond_design, hydro_params, runoff_vol = PondOptimizer.calculate_pond_design(
        catchment_area_m2=c_area_m2,
        slope_pct=outlet_slope,
        land_cover=land_cover,
        runoff_coeff=runoff_coeff,
        rainfall_mm=rainfall_mm,
        lat=target_lat,
        lon=target_lon,
        storage_efficiency=storage_efficiency
    )

    return CatchmentResponse(
        status="success",
        pond_location={
            "lat": target_lat,
            "lon": target_lon,
            "grid_row": target_r,
            "grid_col": target_c,
            "elevation_m": outlet_elev,
            "slope_pct": outlet_slope,
            "selection_mode": selection_mode
        },
        catchment_area=CatchmentAreaMetrics(
            sq_meters=round(c_area_m2, 2),
            hectares=round(c_area_m2 / 10000.0, 3),
            sq_km=round(c_area_m2 / 1e6, 4)
        ),
        hydrology=hydro_params,
        annual_runoff_volume_m3=runoff_vol,
        pond_design=pond_design,
        catchment_geojson=catchment_geo
    )


@app.post("/pond/analyze", tags=["Pond Design"])
@app.post("/api/v1/pond/analyze", tags=["Pond Design"])
async def analyze_pond_design(body: PondAnalyzeRequest):
    """
    Standalone pond design endpoint using Rational Method for pre-computed catchment areas.
    """
    pond_design, hydro_params, runoff_vol = PondOptimizer.calculate_pond_design(
        catchment_area_m2=body.catchment_area_m2,
        slope_pct=3.0,  # Default baseline slope
        land_cover=body.land_cover or LandCoverType.AGRICULTURAL,
        runoff_coeff=body.runoff_coeff,
        rainfall_mm=body.rainfall_mm,
        lat=body.pond_lat,
        lon=body.pond_lon,
        storage_efficiency=body.storage_efficiency or 0.70
    )

    return {
        "status": "success",
        "pond_location": {"lat": body.pond_lat, "lon": body.pond_lon},
        "catchment_area_m2": body.catchment_area_m2,
        "hydrology": hydro_params,
        "annual_runoff_volume_m3": runoff_vol,
        "pond_design": pond_design
    }


@app.post("/processAll", response_model=UnifiedProcessResponse, tags=["Unified Pipeline"])
@app.post("/api/v1/processAll", response_model=UnifiedProcessResponse, tags=["Unified Pipeline"])
async def process_all_unified(
    file: UploadFile = File(..., description="Contour map in KML or KMZ format"),
    pond_lat: Optional[float] = Form(None),
    pond_lon: Optional[float] = Form(None),
    land_cover: LandCoverType = Form(LandCoverType.AGRICULTURAL),
    runoff_coeff: Optional[float] = Form(None),
    rainfall_mm: Optional[float] = Form(None),
    storage_efficiency: float = Form(0.70)
):
    """
    Unified one-shot endpoint returning complete terrain analysis, candidates,
    selected pond watershed delineation, and design parameters.
    """
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty. Please select a valid KML/KMZ contour file.")

    parsed_map, dem, hydro, optimizer = _process_uploaded_kml(content, file.filename or "contour.kml")
    candidates = optimizer.find_candidate_pond_sites(top_k=3)

    if pond_lat is not None and pond_lon is not None:
        target_lat, target_lon = float(pond_lat), float(pond_lon)
        target_r, target_c = dem.geo_to_grid(target_lon, target_lat)
        selection_mode = "Manual coordinate selection"
    else:
        best = candidates[0]
        target_lat, target_lon = best.lat, best.lon
        target_r, target_c = dem.geo_to_grid(target_lon, target_lat)
        selection_mode = "Auto-detected optimal site (Rank 1)"

    outlet_elev = round(dem.get_elevation_at(target_r, target_c), 2)
    outlet_slope = round(dem.get_slope_at(target_r, target_c), 2)

    c_mask, c_area_m2 = hydro.delineate_catchment(target_r, target_c)
    catchment_geo = hydro.catchment_to_geojson(c_mask, target_lat, target_lon, c_area_m2)

    pond_design, hydro_params, runoff_vol = PondOptimizer.calculate_pond_design(
        catchment_area_m2=c_area_m2,
        slope_pct=outlet_slope,
        land_cover=land_cover,
        runoff_coeff=runoff_coeff,
        rainfall_mm=rainfall_mm,
        lat=target_lat,
        lon=target_lon,
        storage_efficiency=storage_efficiency
    )

    contours_geo = parsed_map.to_geojson(max_features=500)

    terrain_resp = TerrainAnalysisResponse(
        status="success",
        filename=file.filename or "contour.kml",
        bounds=BoundingBox(
            min_lon=round(parsed_map.min_lon, 6),
            min_lat=round(parsed_map.min_lat, 6),
            max_lon=round(parsed_map.max_lon, 6),
            max_lat=round(parsed_map.max_lat, 6),
            center_lat=round(parsed_map.center_lat, 6),
            center_lon=round(parsed_map.center_lon, 6),
            width_km=round(parsed_map.width_m / 1000.0, 3),
            height_km=round(parsed_map.height_m / 1000.0, 3),
            area_km2=round(parsed_map.area_km2, 3)
        ),
        elevation_stats=ElevationStats(
            min_m=round(dem.min_elev, 2),
            max_m=round(dem.max_elev, 2),
            mean_m=round(dem.mean_elev, 2),
            relief_m=round(dem.relief, 2)
        ),
        slope_stats=SlopeStats(
            min_pct=round(dem.min_slope_pct, 2),
            max_pct=round(dem.max_slope_pct, 2),
            mean_pct=round(dem.mean_slope_pct, 2),
            flat_area_pct=round(dem.flat_area_pct, 2)
        ),
        contour_count=len(parsed_map.contours),
        total_vertices=parsed_map.total_vertices,
        recommended_pond_sites=candidates,
        contours_geojson=contours_geo
    )

    return UnifiedProcessResponse(
        status="success",
        terrain_analysis=terrain_resp,
        selected_pond_location={
            "lat": target_lat,
            "lon": target_lon,
            "grid_row": target_r,
            "grid_col": target_c,
            "elevation_m": outlet_elev,
            "slope_pct": outlet_slope,
            "selection_mode": selection_mode
        },
        catchment_area=CatchmentAreaMetrics(
            sq_meters=round(c_area_m2, 2),
            hectares=round(c_area_m2 / 10000.0, 3),
            sq_km=round(c_area_m2 / 1e6, 4)
        ),
        hydrology=hydro_params,
        annual_runoff_volume_m3=runoff_vol,
        pond_design=pond_design,
        catchment_geojson=catchment_geo
    )


# Serve Static UI files
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", tags=["UI"])
    async def serve_index():
        return FileResponse(os.path.join(static_dir, "index.html"))
