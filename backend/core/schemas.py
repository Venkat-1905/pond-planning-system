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
    pond_lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude of proposed pond site")
    pond_lon: float = Field(..., ge=-180.0, le=180.0, description="Longitude of proposed pond site")
    catchment_area_m2: float = Field(..., gt=0, description="Upstream catchment area in square meters")
    runoff_coeff: Optional[float] = Field(None, ge=0.1, le=0.9, description="Runoff coefficient (0.1 to 0.9)")
    rainfall_mm: Optional[float] = Field(None, gt=0, description="Annual rainfall in millimeters")
    land_cover: Optional[LandCoverType] = Field(LandCoverType.AGRICULTURAL, description="Land cover type")
    storage_efficiency: Optional[float] = Field(0.70, ge=0.1, le=1.0, description="Storage efficiency ratio")

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


class PondCandidate(BaseModel):
    rank: int
    lat: float
    lon: float
    elevation_m: float
    slope_pct: float
    upstream_cells: int
    estimated_catchment_m2: float
    suitability_score: float = Field(..., ge=0, le=100)
    recommendation: str
    reasons: List[str]


class ElevationStats(BaseModel):
    min_m: float
    max_m: float
    mean_m: float
    relief_m: float


class SlopeStats(BaseModel):
    min_pct: float
    max_pct: float
    mean_pct: float
    flat_area_pct: float  # Slope < 5%


class BoundingBox(BaseModel):
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float
    center_lat: float
    center_lon: float
    width_km: float
    height_km: float
    area_km2: float


class TerrainAnalysisResponse(BaseModel):
    status: str = "success"
    filename: str
    bounds: BoundingBox
    elevation_stats: ElevationStats
    slope_stats: SlopeStats
    contour_count: int
    total_vertices: int
    recommended_pond_sites: List[PondCandidate]
    contours_geojson: Optional[Dict[str, Any]] = None


class PondDesignParameters(BaseModel):
    target_storage_m3: float
    recommended_depth_m: float
    water_depth_m: float
    freeboard_m: float
    top_surface_area_m2: float
    bottom_base_area_m2: float
    length_m: float
    width_m: float
    side_slope_ratio: str = "2:1 (H:V)"
    excavation_volume_m3: float


class CatchmentAreaMetrics(BaseModel):
    sq_meters: float
    hectares: float
    sq_km: float


class HydrologyParameters(BaseModel):
    land_cover: str
    runoff_coefficient: float
    annual_rainfall_mm: float
    rainfall_data_source: str


class CatchmentResponse(BaseModel):
    status: str = "success"
    pond_location: Dict[str, Any]
    catchment_area: CatchmentAreaMetrics
    hydrology: HydrologyParameters
    annual_runoff_volume_m3: float
    pond_design: PondDesignParameters
    catchment_geojson: Dict[str, Any]


class UnifiedProcessResponse(BaseModel):
    status: str = "success"
    terrain_analysis: TerrainAnalysisResponse
    selected_pond_location: Dict[str, Any]
    catchment_area: CatchmentAreaMetrics
    hydrology: HydrologyParameters
    annual_runoff_volume_m3: float
    pond_design: PondDesignParameters
    catchment_geojson: Dict[str, Any]
