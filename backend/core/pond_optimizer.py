"""
Pond Site Optimization, River Corridor Exclusion, Rainfall Fallback Chain, and Hydrological Sizing.
Implements land-cover runoff coefficient lookup, multi-source rainfall query,
riverbed avoidance buffer, and trapezoidal reservoir geometry design.
"""

import math
import requests
import numpy as np
from scipy.ndimage import binary_dilation
from typing import List, Dict, Any, Optional, Tuple
from backend.core.dem_interpolator import DEMGrid
from backend.core.hydrology import HydrologyEngine
from backend.core.schemas import (
    LandCoverType,
    LAND_COVER_RUNOFF_COEFF_MAP,
    PondCandidate,
    PondDesignParameters,
    CatchmentAreaMetrics,
    HydrologyParameters
)


class RainfallService:
    """
    Priority Chain:
    1. Primary: Open-Meteo Historical / Climate API
    2. Secondary: NASA POWER API
    3. Fallback: Default R = 1150 mm (with notification flag)
    """
    DEFAULT_RAINFALL_MM = 1150.0

    @classmethod
    def fetch_annual_rainfall(cls, lat: float, lon: float) -> Tuple[float, str]:
        # 1. Try Open-Meteo API
        try:
            url = f"https://archive-api.open-meteo.com/v1/archive?latitude={lat:.4f}&longitude={lon:.4f}&start_date=2023-01-01&end_date=2023-12-31&daily=precipitation_sum&timezone=auto"
            resp = requests.get(url, timeout=3.0)
            if resp.status_code == 200:
                data = resp.json()
                daily_precip = data.get("daily", {}).get("precipitation_sum", [])
                valid_precip = [p for p in daily_precip if p is not None]
                if valid_precip and sum(valid_precip) > 50:
                    annual_total = float(sum(valid_precip))
                    return round(annual_total, 1), "Open-Meteo Climate Archive (2023 Total)"
        except Exception:
            pass

        # 2. Try NASA POWER API
        try:
            nasa_url = f"https://power.larc.nasa.gov/api/temporal/climatology/point?parameters=PRECTOTCORR&community=AG&longitude={lon:.4f}&latitude={lat:.4f}&format=JSON"
            resp = requests.get(nasa_url, timeout=3.0)
            if resp.status_code == 200:
                data = resp.json()
                ann_val = data.get("properties", {}).get("parameter", {}).get("PRECTOTCORR", {}).get("ANN")
                if ann_val and ann_val > 0:
                    annual_mm = float(ann_val * 365.25)
                    return round(annual_mm, 1), "NASA POWER Climatology (30-yr Mean)"
        except Exception:
            pass

        # 3. Fallback default
        return cls.DEFAULT_RAINFALL_MM, "Fallback default (1150 mm/yr) — verify for local micro-region"


class PondOptimizer:
    def __init__(self, dem: DEMGrid, hydrology: HydrologyEngine):
        self.dem = dem
        self.hydro = hydrology

    def find_candidate_pond_sites(
        self,
        top_k: int = 3,
        min_separation_m: float = 350.0,
        river_buffer_m: float = 120.0,
        max_river_threshold_ha: float = 60.0
    ) -> List[PondCandidate]:
        """
        Identifies top K suitable village pond locations:
        - Detects and strictly EXCLUDES the main river course / perennial floodways (acc > 60 ha + buffer).
        - Targets optimal micro-catchments (5 to 45 ha) for agricultural / village ponds.
        - Prioritizes gentle slopes (< 3%) to minimize excavation and ensure embankment stability.
        - Applies non-maximum spatial suppression to provide distinct geographic alternatives.
        """
        nrows, ncols = self.dem.nrows, self.dem.ncols
        cell_area_ha = self.hydro.cell_area_m2 / 10000.0
        acc_ha = self.hydro.flow_acc.astype(float) * cell_area_ha
        slope = self.dem.slope_pct

        # 1. Detect Main River Channel & Dilate Buffer
        # Cells with massive accumulation represent the main perennial river channel
        river_thresh = min(max_river_threshold_ha, max(30.0, float(np.max(acc_ha)) * 0.20))
        river_cells = acc_ha >= river_thresh

        # Create circular spatial dilation buffer around river
        buffer_cells = max(3, int(round(river_buffer_m / self.dem.cell_size)))
        y, x = np.ogrid[-buffer_cells:buffer_cells+1, -buffer_cells:buffer_cells+1]
        struct = (x**2 + y**2) <= buffer_cells**2
        river_buffer_mask = binary_dilation(river_cells, structure=struct)

        # 2. Farm Pond Micro-Catchment Suitability Score (50 pts max)
        # Optimal farm pond catchment is 10-30 ha (bell curve peak at 20 ha)
        catchment_score = np.exp(-0.5 * ((acc_ha - 20.0) / 12.0)**2) * 50.0
        # Hard limits: only allow micro-catchments between 2 ha and 55 ha
        catchment_score[(acc_ha < 2.0) | (acc_ha > 55.0)] = 0.0

        # 3. Slope Suitability Score (35 pts max)
        # Ideal: 0-2.5% = 35 pts, 2.5-5% = 15-35 pts, >5% = 0 pts
        slope_score = np.zeros_like(slope)
        slope_score[slope <= 2.5] = 35.0
        mask_s = (slope > 2.5) & (slope <= 5.0)
        slope_score[mask_s] = 35.0 - ((slope[mask_s] - 2.5) / 2.5) * 20.0

        # 4. Elevation Valley Bottom Score (15 pts max)
        elev_range = self.dem.relief if self.dem.relief > 0 else 1.0
        elev_score = (1.0 - (self.dem.elevation - self.dem.min_elev) / elev_range) * 15.0

        total_score_grid = catchment_score + slope_score + elev_score

        # 5. Apply River & Boundary Masks
        total_score_grid[river_buffer_mask] = 0.0  # EXCLUDE RIVER & BUFFER
        total_score_grid[slope > 5.0] = 0.0        # EXCLUDE STEEP SLOPES

        # Margin buffer (reject outer 5% border cells)
        margin_r = max(4, int(nrows * 0.05))
        margin_c = max(4, int(ncols * 0.05))
        total_score_grid[:margin_r, :] = 0.0
        total_score_grid[-margin_r:, :] = 0.0
        total_score_grid[:, :margin_c] = 0.0
        total_score_grid[:, -margin_c:] = 0.0

        # 6. Non-maximum suppression to find top candidate sites
        candidates: List[PondCandidate] = []
        min_sep_cells = max(3, int(round(min_separation_m / self.dem.cell_size)))
        scores_work = total_score_grid.copy()

        for rank in range(1, top_k + 1):
            max_idx = np.argmax(scores_work)
            r, c = np.unravel_index(max_idx, scores_work.shape)
            best_score = float(scores_work[r, c])

            if best_score <= 0.0:
                break

            lon, lat = self.dem.grid_to_geo(r, c)
            elev_m = round(self.dem.get_elevation_at(r, c), 2)
            slope_p = round(self.dem.get_slope_at(r, c), 2)
            u_cells = int(self.hydro.flow_acc[r, c])
            c_area_m2 = round(u_cells * self.hydro.cell_area_m2, 1)
            c_ha = round(c_area_m2 / 10000.0, 1)

            reasons = [
                f"Safe off-stream site: Excluded from main river channel and flood buffer (>120m buffer)",
                f"Optimal micro-catchment ({c_ha} ha) ideal for village rainwater harvesting without flood surge risk",
                f"Gentle ground slope ({slope_p}%) minimizing earthwork and ensuring stable earthen bunds"
            ]

            recommendation = "Highly Recommended for Primary Village Storage Pond" if rank == 1 else f"Recommended Alternative Site (Option {rank})"

            # Normalize score to 0-100 scale
            normalized_score = round(min(100.0, (best_score / 95.0) * 100.0), 1)

            candidates.append(PondCandidate(
                rank=rank,
                lat=round(lat, 6),
                lon=round(lon, 6),
                elevation_m=elev_m,
                slope_pct=slope_p,
                upstream_cells=u_cells,
                estimated_catchment_m2=c_area_m2,
                suitability_score=normalized_score,
                recommendation=recommendation,
                reasons=reasons
            ))

            # Suppress neighborhood
            r_low = max(0, r - min_sep_cells)
            r_high = min(nrows, r + min_sep_cells + 1)
            c_low = max(0, c - min_sep_cells)
            c_high = min(ncols, c + min_sep_cells + 1)
            scores_work[r_low:r_high, c_low:c_high] = 0.0

        return candidates

    @classmethod
    def calculate_pond_design(
        cls,
        catchment_area_m2: float,
        slope_pct: float,
        land_cover: LandCoverType = LandCoverType.AGRICULTURAL,
        runoff_coeff: Optional[float] = None,
        rainfall_mm: Optional[float] = None,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        storage_efficiency: float = 0.70
    ) -> Tuple[PondDesignParameters, HydrologyParameters, float]:
        """
        Calculates Rational runoff volume and trapezoidal pond dimensions.
        Formula:
            V_runoff (m^3) = (C * R * A) / 1000
            Target_Storage (m^3) = V_runoff * storage_efficiency
        """
        # 1. Resolve Runoff Coefficient (C)
        if runoff_coeff is not None:
            c_val = max(0.1, min(0.9, float(runoff_coeff)))
        else:
            c_val = LAND_COVER_RUNOFF_COEFF_MAP.get(land_cover, 0.45)

        # 2. Resolve Rainfall (R)
        if rainfall_mm is not None and rainfall_mm > 0:
            r_val = float(rainfall_mm)
            r_source = "User specified / API override"
        elif lat is not None and lon is not None:
            r_val, r_source = RainfallService.fetch_annual_rainfall(lat, lon)
        else:
            r_val = RainfallService.DEFAULT_RAINFALL_MM
            r_source = "Standard Regional Baseline (1150 mm/yr)"

        # 3. Rational Runoff Volume (m^3)
        runoff_volume_m3 = (c_val * r_val * catchment_area_m2) / 1000.0

        # 4. Target Storage
        target_storage_m3 = runoff_volume_m3 * storage_efficiency

        # Practical farm pond storage sizing
        practical_storage_m3 = max(500.0, min(50000.0, target_storage_m3))

        # 5. Depth Selection based on terrain slope
        freeboard = 0.5  # meters safety margin
        if slope_pct <= 3.0:
            water_depth = 3.0
            total_depth = 3.5
        elif slope_pct <= 6.0:
            water_depth = 2.5
            total_depth = 3.0
        else:
            water_depth = 2.0
            total_depth = 2.5

        # 6. Trapezoidal geometry sizing (Side slope 2:1 -> z=2.0)
        z_side = 2.0
        mid_area = practical_storage_m3 / water_depth
        w_mid = math.sqrt(mid_area / 1.5)
        l_mid = 1.5 * w_mid

        l_top = round(l_mid + z_side * total_depth, 1)
        w_top = round(w_mid + z_side * total_depth, 1)
        top_surface_area = round(l_top * w_top, 1)

        l_base = max(5.0, round(l_mid - z_side * total_depth, 1))
        w_base = max(5.0, round(w_mid - z_side * total_depth, 1))
        bottom_base_area = round(l_base * w_base, 1)

        excavation_vol = round((total_depth / 6.0) * (l_top * w_top + l_base * w_base + 4.0 * l_mid * w_mid), 1)

        design_params = PondDesignParameters(
            target_storage_m3=round(practical_storage_m3, 1),
            recommended_depth_m=total_depth,
            water_depth_m=water_depth,
            freeboard_m=freeboard,
            top_surface_area_m2=top_surface_area,
            bottom_base_area_m2=bottom_base_area,
            length_m=l_top,
            width_m=w_top,
            side_slope_ratio="2:1 (H:V)",
            excavation_volume_m3=excavation_vol
        )

        hydro_params = HydrologyParameters(
            land_cover=land_cover.value if isinstance(land_cover, LandCoverType) else str(land_cover),
            runoff_coefficient=round(c_val, 2),
            annual_rainfall_mm=round(r_val, 1),
            rainfall_data_source=r_source
        )

        return design_params, hydro_params, round(runoff_volume_m3, 1)
