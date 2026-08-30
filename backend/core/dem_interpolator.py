"""
Digital Elevation Model (DEM) Reconstruction & Slope Analysis Engine.
Interpolates sparse contour isolines into continuous high-resolution raster grids,
calculates terrain gradients, and handles geospatial coordinate transformations.
"""

import numpy as np
from scipy.interpolate import griddata
from scipy.ndimage import gaussian_filter
from typing import Tuple, Dict, Any, Optional
from backend.core.kml_parser import ParsedContourMap, MetricProjector


class DEMGrid:
    def __init__(
        self,
        elevation_grid: np.ndarray,
        x_coords: np.ndarray,
        y_coords: np.ndarray,
        cell_size: float,
        projector: MetricProjector,
        min_elev: float,
        max_elev: float
    ):
        self.elevation = elevation_grid  # 2D array [nrows, ncols] (y down/up, x across)
        self.x_coords = x_coords        # 1D array of metric X
        self.y_coords = y_coords        # 1D array of metric Y (descending: index 0 is north/max_y)
        self.cell_size = cell_size
        self.projector = projector
        self.nrows, self.ncols = elevation_grid.shape

        self.min_elev = float(np.min(elevation_grid))
        self.max_elev = float(np.max(elevation_grid))
        self.mean_elev = float(np.mean(elevation_grid))
        self.relief = self.max_elev - self.min_elev

        self._compute_slope()

    def _compute_slope(self):
        """
        Computes slope in percentage and degrees using 2D finite difference gradients.
        """
        # Note: y_coords descending, so spacing is -cell_size in y direction
        dz_dy, dz_dx = np.gradient(self.elevation, self.cell_size, self.cell_size)
        gradient_mag = np.sqrt(dz_dx**2 + dz_dy**2)

        self.slope_pct = gradient_mag * 100.0
        self.slope_deg = np.degrees(np.arctan(gradient_mag))

        self.min_slope_pct = float(np.min(self.slope_pct))
        self.max_slope_pct = float(np.max(self.slope_pct))
        self.mean_slope_pct = float(np.mean(self.slope_pct))

        # Percentage of land suitable for ponds (slope < 5%)
        flat_cells = np.sum(self.slope_pct < 5.0)
        self.flat_area_pct = float((flat_cells / self.slope_pct.size) * 100.0)

    def geo_to_grid(self, lon: float, lat: float) -> Tuple[int, int]:
        """Converts WGS84 (lon, lat) to raster (row, col)."""
        x, y = self.projector.to_metric(lon, lat)
        return self.metric_to_grid(x, y)

    def grid_to_geo(self, row: int, col: int) -> Tuple[float, float]:
        """Converts raster (row, col) to WGS84 (lon, lat)."""
        x, y = self.grid_to_metric(row, col)
        return self.projector.to_geo(x, y)

    def metric_to_grid(self, x: float, y: float) -> Tuple[int, int]:
        col = int(np.clip(round((x - self.x_coords[0]) / self.cell_size), 0, self.ncols - 1))
        # y_coords[0] is top (max_y)
        row = int(np.clip(round((self.y_coords[0] - y) / self.cell_size), 0, self.nrows - 1))
        return row, col

    def grid_to_metric(self, row: float, col: float) -> Tuple[float, float]:
        col = max(0.0, min(float(self.ncols - 1), float(col)))
        row = max(0.0, min(float(self.nrows - 1), float(row)))
        x0 = float(self.x_coords[0])
        y0 = float(self.y_coords[0])
        x = x0 + col * self.cell_size
        y = y0 - row * self.cell_size
        return x, y

    def get_slope_at(self, row: int, col: int) -> float:
        return float(self.slope_pct[row, col])

    def get_elevation_at(self, row: int, col: int) -> float:
        return float(self.elevation[row, col])


def generate_dem_from_contours(
    parsed_map: ParsedContourMap,
    target_cell_size: Optional[float] = None,
    smooth_sigma: float = 0.8
) -> DEMGrid:
    """
    Reconstructs continuous DEM grid from parsed contour lines using Delaunay-based interpolation.
    """
    points_xy, values_z = parsed_map.get_points_cloud()
    points_arr = np.array(points_xy)
    values_arr = np.array(values_z)

    # Subsample points if cloud is extremely dense (> 50,000 pts) for fast interpolation
    if len(points_arr) > 40000:
        step = max(1, len(points_arr) // 40000)
        points_arr = points_arr[::step]
        values_arr = values_arr[::step]

    # Metric bounds
    x_min, y_min = parsed_map.projector.to_metric(parsed_map.min_lon, parsed_map.min_lat)
    x_max, y_max = parsed_map.projector.to_metric(parsed_map.max_lon, parsed_map.max_lat)

    width = x_max - x_min
    height = y_max - y_min

    # Adapt cell size if not provided: aims for ~250-350 cells along major axis
    if target_cell_size is None or target_cell_size <= 0:
        max_dim = max(width, height)
        target_cell_size = max(5.0, min(20.0, max_dim / 300.0))

    x_grid = np.arange(x_min, x_max + target_cell_size, target_cell_size)
    # North-to-south (descending Y)
    y_grid = np.arange(y_max, y_min - target_cell_size, -target_cell_size)

    grid_x_2d, grid_y_2d = np.meshgrid(x_grid, y_grid)

    # 1. Linear interpolation (TIN-equivalent)
    dem_linear = griddata(points_arr, values_arr, (grid_x_2d, grid_y_2d), method="linear")

    # 2. Nearest-neighbor for any edge NaNs outside convex hull
    if np.isnan(dem_linear).any():
        dem_nearest = griddata(points_arr, values_arr, (grid_x_2d, grid_y_2d), method="nearest")
        dem_linear[np.isnan(dem_linear)] = dem_nearest[np.isnan(dem_linear)]

    # 3. Gaussian smoothing to avoid terracing
    if smooth_sigma > 0:
        dem_smooth = gaussian_filter(dem_linear, sigma=smooth_sigma)
    else:
        dem_smooth = dem_linear

    return DEMGrid(
        elevation_grid=dem_smooth,
        x_coords=x_grid,
        y_coords=y_grid,
        cell_size=target_cell_size,
        projector=parsed_map.projector,
        min_elev=parsed_map.min_elev,
        max_elev=parsed_map.max_elev
    )
