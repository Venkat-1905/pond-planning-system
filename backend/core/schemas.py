"""
Pydantic schemas and data transfer objects with strict validation.
"""

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator


class LandCoverType(str, Enum):
    FOREST = "forest"
    DENSE_VEGETATION = "dense_vegetation"
    AGRICULTURAL = "agricultural"
    MIXED = "mixed"
    BARREN = "barren"
    ROCKY = "rocky"
    URBAN = "urban"


LAND_COVER_RUNOFF_COEFF_MAP = {
    LandCoverType.FOREST: 0.30,
    LandCoverType.DENSE_VEGETATION: 0.30,
    LandCoverType.AGRICULTURAL: 0.45,
    LandCoverType.MIXED: 0.45,
    LandCoverType.BARREN: 0.65,
    LandCoverType.ROCKY: 0.65,
    LandCoverType.URBAN: 0.70,
}


class PondAnalyzeRequest(BaseModel):
    pond_lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude of proposed pond site", examples=[21.25795])
    pond_lon: float = Field(..., ge=-180.0, le=180.0, description="Longitude of proposed pond site", examples=[81.30098])
    catchment_area_m2: float = Field(..., gt=0, description="Upstream catchment area in square meters", examples=[152000.0])
    runoff_coeff: Optional[float] = Field(None, ge=0.1, le=0.9, description="Runoff coefficient (0.1 to 0.9)", examples=[0.45])
    rainfall_mm: Optional[float] = Field(None, gt=0, description="Annual rainfall in millimeters", examples=[1150.0])
    land_cover: Optional[LandCoverType] = Field(LandCoverType.AGRICULTURAL, description="Land cover type")
    storage_efficiency: Optional[float] = Field(0.70, ge=0.1, le=1.0, description="Storage efficiency ratio", examples=[0.70])

    @field_validator("runoff_coeff")
    @classmethod
    def validate_runoff_coeff(cls, v):
        if v is not None and not (0.1 <= v <= 0.9):
            raise ValueError("Runoff coefficient C must be between 0.1 and 0.9")
        return v

    @field_validator("rainfall_mm")
    @classmethod
    def validate_rainfall(cls, v):
        if v is not None and v <= 0:
            raise ValueError("Rainfall depth R must be strictly positive")
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "pond_lat": 21.257951,
                "pond_lon": 81.300983,
                "catchment_area_m2": 152000.0,
                "runoff_coeff": 0.45,
                "rainfall_mm": 1150.0,
                "land_cover": "agricultural",
                "storage_efficiency": 0.70
            }
        }
    }


class PondCandidate(BaseModel):
    rank: int = Field(..., examples=[1])
    lat: float = Field(..., examples=[21.257951])
    lon: float = Field(..., examples=[81.300983])
    elevation_m: float = Field(..., examples=[279.44])
    slope_pct: float = Field(..., examples=[0.10])
    upstream_cells: int = Field(..., examples=[152])
    estimated_catchment_m2: float = Field(..., examples=[152000.0])
    suitability_score: float = Field(..., ge=0, le=100, examples=[96.6])
    recommendation: str = Field(..., examples=["Highly Recommended for Primary Village Storage Pond (Natural Retention Bowl)"])
    reasons: List[str] = Field(..., examples=[[
        "Natural retention amphitheater (TPI: -8.12m): Natural terrain bowl provides maximum storage with minimal earth excavation",
        "Safe off-stream site: Excluded from main river channel and flood buffer (>180m buffer)",
        "Gentle ground slope (0.1%) ensuring high embankment stability and minimal seepage"
    ]])


class ElevationStats(BaseModel):
    min_m: float = Field(..., examples=[267.02])
    max_m: float = Field(..., examples=[297.58])
    mean_m: float = Field(..., examples=[281.35])
    relief_m: float = Field(..., examples=[30.56])


class SlopeStats(BaseModel):
    min_pct: float = Field(..., examples=[0.0])
    max_pct: float = Field(..., examples=[18.42])
    mean_pct: float = Field(..., examples=[2.85])
    flat_area_pct: float = Field(..., examples=[55.25])


class BoundingBox(BaseModel):
    min_lon: float = Field(..., examples=[81.272105])
    min_lat: float = Field(..., examples=[21.238912])
    max_lon: float = Field(..., examples=[81.315480])
    max_lat: float = Field(..., examples=[21.268421])
    center_lat: float = Field(..., examples=[21.253666])
    center_lon: float = Field(..., examples=[81.293792])
    width_km: float = Field(..., examples=[4.512])
    height_km: float = Field(..., examples=[3.275])
    area_km2: float = Field(..., examples=[14.776])


class TerrainAnalysisResponse(BaseModel):
    status: str = Field("success", examples=["success"])
    filename: str = Field(..., examples=["contours_1m.kml"])
    bounds: BoundingBox
    elevation_stats: ElevationStats
    slope_stats: SlopeStats
    contour_count: int = Field(..., examples=[1355])
    total_vertices: int = Field(..., examples=[128450])
    recommended_pond_sites: List[PondCandidate]
    contours_geojson: Optional[Dict[str, Any]] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "success",
                "filename": "contours_1m.kml",
                "bounds": {
                    "min_lon": 81.272105,
                    "min_lat": 21.238912,
                    "max_lon": 81.315480,
                    "max_lat": 21.268421,
                    "center_lat": 21.253666,
                    "center_lon": 81.293792,
                    "width_km": 4.512,
                    "height_km": 3.275,
                    "area_km2": 14.776
                },
                "elevation_stats": {
                    "min_m": 267.02,
                    "max_m": 297.58,
                    "mean_m": 281.35,
                    "relief_m": 30.56
                },
                "slope_stats": {
                    "min_pct": 0.0,
                    "max_pct": 18.42,
                    "mean_pct": 2.85,
                    "flat_area_pct": 55.25
                },
                "contour_count": 1355,
                "total_vertices": 128450,
                "recommended_pond_sites": [
                    {
                        "rank": 1,
                        "lat": 21.257951,
                        "lon": 81.300983,
                        "elevation_m": 279.44,
                        "slope_pct": 0.1,
                        "upstream_cells": 152,
                        "estimated_catchment_m2": 152000.0,
                        "suitability_score": 96.6,
                        "recommendation": "Highly Recommended for Primary Village Storage Pond (Natural Retention Bowl)",
                        "reasons": [
                            "Natural retention amphitheater (TPI: -8.12m): Natural terrain bowl provides maximum storage with minimal earth excavation",
                            "Safe off-stream site: Excluded from main river channel and flood buffer (>180m buffer)",
                            "Gentle ground slope (0.1%) ensuring high embankment stability and minimal seepage"
                        ]
                    }
                ],
                "contours_geojson": None
            }
        }
    }


class PondDesignParameters(BaseModel):
    target_storage_m3: float = Field(..., examples=[76432.5])
    recommended_depth_m: float = Field(..., examples=[3.5])
    water_depth_m: float = Field(..., examples=[3.0])
    freeboard_m: float = Field(..., examples=[0.5])
    top_surface_area_m2: float = Field(..., examples=[21450.2])
    bottom_base_area_m2: float = Field(..., examples=[17205.8])
    length_m: float = Field(..., examples=[180.2])
    width_m: float = Field(..., examples=[119.0])
    side_slope_ratio: str = Field("2:1 (H:V)", examples=["2:1 (H:V)"])
    excavation_volume_m3: float = Field(..., examples=[89240.0])


class CatchmentAreaMetrics(BaseModel):
    sq_meters: float = Field(..., examples=[152001.0])
    hectares: float = Field(..., examples=[15.2])
    sq_km: float = Field(..., examples=[0.152])


class HydrologyParameters(BaseModel):
    land_cover: str = Field(..., examples=["agricultural"])
    runoff_coefficient: float = Field(..., examples=[0.45])
    annual_rainfall_mm: float = Field(..., examples=[1150.0])
    rainfall_data_source: str = Field(..., examples=["NASA POWER Climatology (30-yr Mean)"])


class CatchmentResponse(BaseModel):
    status: str = Field("success", examples=["success"])
    pond_location: Dict[str, Any] = Field(..., examples=[{
        "lat": 21.257951,
        "lon": 81.300983,
        "grid_row": 120,
        "grid_col": 215,
        "elevation_m": 279.44,
        "slope_pct": 0.10,
        "selection_mode": "Auto-detected optimal site (Rank 1)"
    }])
    catchment_area: CatchmentAreaMetrics
    hydrology: HydrologyParameters
    annual_runoff_volume_m3: float = Field(..., examples=[109188.0])
    pond_design: PondDesignParameters
    catchment_geojson: Dict[str, Any]

    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "success",
                "pond_location": {
                    "lat": 21.257951,
                    "lon": 81.300983,
                    "grid_row": 120,
                    "grid_col": 215,
                    "elevation_m": 279.44,
                    "slope_pct": 0.10,
                    "selection_mode": "Auto-detected optimal site (Rank 1)"
                },
                "catchment_area": {
                    "sq_meters": 152001.0,
                    "hectares": 15.2,
                    "sq_km": 0.152
                },
                "hydrology": {
                    "land_cover": "agricultural",
                    "runoff_coefficient": 0.45,
                    "annual_rainfall_mm": 1150.0,
                    "rainfall_data_source": "NASA POWER Climatology (30-yr Mean)"
                },
                "annual_runoff_volume_m3": 109188.0,
                "pond_design": {
                    "target_storage_m3": 76432.5,
                    "recommended_depth_m": 3.5,
                    "water_depth_m": 3.0,
                    "freeboard_m": 0.5,
                    "top_surface_area_m2": 21450.2,
                    "bottom_base_area_m2": 17205.8,
                    "length_m": 180.2,
                    "width_m": 119.0,
                    "side_slope_ratio": "2:1 (H:V)",
                    "excavation_volume_m3": 89240.0
                },
                "catchment_geojson": {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[81.300, 21.257], [81.305, 21.258], [81.300, 21.257]]]
                    },
                    "properties": {
                        "area_m2": 152001.0,
                        "area_ha": 15.2
                    }
                }
            }
        }
    }


class UnifiedProcessResponse(BaseModel):
    status: str = Field("success", examples=["success"])
    terrain_analysis: TerrainAnalysisResponse
    selected_pond_location: Dict[str, Any]
    catchment_area: CatchmentAreaMetrics
    hydrology: HydrologyParameters
    annual_runoff_volume_m3: float = Field(..., examples=[109188.0])
    pond_design: PondDesignParameters
    catchment_geojson: Dict[str, Any]
