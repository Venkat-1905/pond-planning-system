"""
Hydrological Modeling Engine:
- Sink / Depression filling & gradient conditioning (Priority-Flood)
- D8 Flow Direction calculation
- Flow Accumulation matrix calculation in O(N)
- Reverse-flow Watershed / Catchment Delineation
- Fast GeoJSON boundary polygonization using contourpy & shapely
"""

import heapq
from collections import deque
import numpy as np
import contourpy
from shapely.geometry import Polygon, MultiPolygon, mapping
from shapely.ops import unary_union
from typing import Tuple, List, Dict, Any, Optional
from backend.core.dem_interpolator import DEMGrid


# 8 Neighbors: (dr, dc, distance_weight, direction_code)
# Direction indices: 0:E, 1:SE, 2:S, 3:SW, 4:W, 5:NW, 6:N, 7:NE
D8_OFFSETS = [
    (0, 1, 1.0),        # 0: East
    (1, 1, 1.41421356), # 1: South-East
    (1, 0, 1.0),        # 2: South
    (1, -1, 1.41421356),# 3: South-West
    (0, -1, 1.0),       # 4: West
    (-1, -1, 1.41421356),# 5: North-West
    (-1, 0, 1.0),       # 6: North
    (-1, 1, 1.41421356) # 7: North-East
]


class HydrologyEngine:
    def __init__(self, dem: DEMGrid):
        self.dem = dem
        self.nrows = dem.nrows
        self.ncols = dem.ncols
        self.cell_size = dem.cell_size
        self.cell_area_m2 = self.cell_size * self.cell_size

        # 1. Fill depressions / condition DEM
        self.filled_dem = self._fill_depressions(dem.elevation)

        # 2. Compute D8 Flow Direction
        self.flow_dir, self.downstream_target = self._compute_d8_flow_dir(self.filled_dem)

        # 3. Compute Flow Accumulation
        self.flow_acc = self._compute_flow_accumulation()

    def _fill_depressions(self, elevation: np.ndarray) -> np.ndarray:
        """
        Priority-Flood depression filling algorithm (Wang & Liu 2006).
        Monotonically resolves sinks while creating subtle flow gradients.
        """
        nrows, ncols = elevation.shape
        filled = np.full((nrows, ncols), np.inf, dtype=np.float64)
        visited = np.zeros((nrows, ncols), dtype=bool)
        pq: List[Tuple[float, int, int]] = []

        # Boundaries as starting seed outlets
        for r in range(nrows):
            for c in (0, ncols - 1):
                filled[r, c] = elevation[r, c]
                visited[r, c] = True
                heapq.heappush(pq, (elevation[r, c], r, c))

        for c in range(ncols):
            for r in (0, nrows - 1):
                if not visited[r, c]:
                    filled[r, c] = elevation[r, c]
                    visited[r, c] = True
                    heapq.heappush(pq, (elevation[r, c], r, c))

        eps = 1e-5
        while pq:
            elev_val, r, c = heapq.heappop(pq)
            for dr, dc, _ in D8_OFFSETS:
                nr, nc = r + dr, c + dc
                if 0 <= nr < nrows and 0 <= nc < ncols and not visited[nr, nc]:
                    visited[nr, nc] = True
                    new_elev = max(elevation[nr, nc], elev_val + eps)
                    filled[nr, nc] = new_elev
                    heapq.heappush(pq, (new_elev, nr, nc))

        return filled

    def _compute_d8_flow_dir(self, dem_matrix: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Calculates D8 flow direction matrix.
        Returns:
            flow_dir: [nrows, ncols] direction index (0..7, or -1 for pit/boundary)
            downstream_target: [nrows, ncols, 2] target (r, c) coordinate
        """
        nrows, ncols = self.nrows, self.ncols
        flow_dir = np.full((nrows, ncols), -1, dtype=np.int32)
        downstream_target = np.full((nrows, ncols, 2), -1, dtype=np.int32)

        for r in range(nrows):
            for c in range(ncols):
                center_z = dem_matrix[r, c]
                max_slope = 0.0
                best_dir = -1
                best_nr, best_nc = -1, -1

                for d_idx, (dr, dc, dist_wt) in enumerate(D8_OFFSETS):
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < nrows and 0 <= nc < ncols:
                        drop = center_z - dem_matrix[nr, nc]
                        slope = drop / (dist_wt * self.cell_size)
                        if slope > max_slope:
                            max_slope = slope
                            best_dir = d_idx
                            best_nr, best_nc = nr, nc

                if best_dir != -1:
                    flow_dir[r, c] = best_dir
                    downstream_target[r, c, 0] = best_nr
                    downstream_target[r, c, 1] = best_nc

        return flow_dir, downstream_target

    def _compute_flow_accumulation(self) -> np.ndarray:
        """
        Computes flow accumulation (upstream contributing cell count) in O(N).
        """
        nrows, ncols = self.nrows, self.ncols
        in_degree = np.zeros((nrows, ncols), dtype=np.int32)

        for r in range(nrows):
            for c in range(ncols):
                nr, nc = self.downstream_target[r, c]
                if nr != -1 and nc != -1:
                    in_degree[nr, nc] += 1

        queue = deque()
        for r in range(nrows):
            for c in range(ncols):
                if in_degree[r, c] == 0:
                    queue.append((r, c))

        accumulation = np.ones((nrows, ncols), dtype=np.int32)

        while queue:
            r, c = queue.popleft()
            nr, nc = self.downstream_target[r, c]
            if nr != -1 and nc != -1:
                accumulation[nr, nc] += accumulation[r, c]
                in_degree[nr, nc] -= 1
                if in_degree[nr, nc] == 0:
                    queue.append((nr, nc))

        return accumulation

    def delineate_catchment(self, outlet_row: int, outlet_col: int) -> Tuple[np.ndarray, float]:
        """
        Delineates upstream contributing watershed from outlet (outlet_row, outlet_col).
        """
        nrows, ncols = self.nrows, self.ncols
        outlet_row = max(0, min(nrows - 1, outlet_row))
        outlet_col = max(0, min(ncols - 1, outlet_col))

        upstream_map: Dict[Tuple[int, int], List[Tuple[int, int]]] = {}
        for r in range(nrows):
            for c in range(ncols):
                nr, nc = self.downstream_target[r, c]
                if nr != -1 and nc != -1:
                    target_key = (int(nr), int(nc))
                    if target_key not in upstream_map:
                        upstream_map[target_key] = []
                    upstream_map[target_key].append((r, c))

        catchment_mask = np.zeros((nrows, ncols), dtype=bool)
        queue = deque([(outlet_row, outlet_col)])
        catchment_mask[outlet_row, outlet_col] = True

        while queue:
            curr = queue.popleft()
            if curr in upstream_map:
                for up_cell in upstream_map[curr]:
                    ur, uc = up_cell
                    if not catchment_mask[ur, uc]:
                        catchment_mask[ur, uc] = True
                        queue.append((ur, uc))

        cell_count = int(np.sum(catchment_mask))
        catchment_area_m2 = float(cell_count * self.cell_area_m2)

        return catchment_mask, catchment_area_m2

    def catchment_to_geojson(self, catchment_mask: np.ndarray, outlet_lat: float, outlet_lon: float, area_m2: float) -> Dict[str, Any]:
        """
        Vectorizes binary catchment mask into a standard GeoJSON Polygon feature.
        """
        padded_mask = np.pad(catchment_mask.astype(float), pad_width=1, mode="constant", constant_values=0.0)
        c_gen = contourpy.contour_generator(z=padded_mask)
        lines = c_gen.lines(0.5)

        polygon_geometries = []
        for line in lines:
            # line is array of [x, y] coordinates in grid space (x=col, y=row)
            # Subtract padding offset
            c_pts = line[:, 0] - 1.0
            r_pts = line[:, 1] - 1.0

            geo_coords = []
            for c, r in zip(c_pts, r_pts):
                lon, lat = self.dem.grid_to_geo(int(round(r)), int(round(c)))
                geo_coords.append((lon, lat))

            if len(geo_coords) >= 4:
                try:
                    poly = Polygon(geo_coords)
                    if poly.is_valid and poly.area > 0:
                        polygon_geometries.append(poly)
                    else:
                        poly_clean = poly.buffer(0)
                        if not poly_clean.is_empty:
                            polygon_geometries.append(poly_clean)
                except Exception:
                    pass

        if polygon_geometries:
            merged_poly = unary_union(polygon_geometries)
            simplified_poly = merged_poly.simplify(0.00005, preserve_topology=True)
            geom_json = mapping(simplified_poly)
        else:
            # Fallback box around outlet
            d = 0.001
            geom_json = {
                "type": "Polygon",
                "coordinates": [[
                    [outlet_lon - d, outlet_lat - d],
                    [outlet_lon + d, outlet_lat - d],
                    [outlet_lon + d, outlet_lat + d],
                    [outlet_lon - d, outlet_lat + d],
                    [outlet_lon - d, outlet_lat - d]
                ]]
            }

        return {
            "type": "Feature",
            "properties": {
                "outlet": {"lat": outlet_lat, "lon": outlet_lon},
                "area_m2": round(area_m2, 2),
                "area_hectares": round(area_m2 / 10000.0, 3),
                "area_sq_km": round(area_m2 / 1e6, 4)
            },
            "geometry": geom_json
        }
