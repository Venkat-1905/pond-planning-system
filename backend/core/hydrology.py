"""
D8 Hydrological Routing, Priority-Flood Depression Resolution, Flow Accumulation,
and Watershed Catchment Delineation Engine.
"""

import math
import heapq
import numpy as np
from collections import deque
import contourpy
from typing import Tuple, Dict, Any, List
from backend.core.dem_interpolator import DEMGrid


class HydrologyEngine:
    def __init__(self, dem: DEMGrid):
        self.dem = dem
        self.nrows = dem.nrows
        self.ncols = dem.ncols
        self.cell_size = dem.cell_size
        self.cell_area_m2 = dem.cell_size ** 2

        # 1. Fill depressions
        self.filled_dem = self._fill_depressions_priority_flood(dem.elevation)

        # 2. D8 Flow Directions & Downstream targets
        self.flow_dir, self.downstream_target = self._compute_d8_flow_directions(self.filled_dem)

        # 3. Flow Accumulation
        self.flow_acc = self._compute_flow_accumulation()

    def _fill_depressions_priority_flood(self, elevation: np.ndarray) -> np.ndarray:
        """
        Priority-Flood algorithm (Barnes et al., 2014) to fill spurious single-cell DEM pits.
        """
        nrows, ncols = self.nrows, self.ncols
        filled = np.full((nrows, ncols), np.inf, dtype=np.float64)
        pq: List[Tuple[float, int, int]] = []

        # Push edge cells
        for r in range(nrows):
            for c in (0, ncols - 1):
                filled[r, c] = elevation[r, c]
                heapq.heappush(pq, (float(elevation[r, c]), r, c))
        for c in range(ncols):
            for r in (0, nrows - 1):
                if filled[r, c] == np.inf:
                    filled[r, c] = elevation[r, c]
                    heapq.heappush(pq, (float(elevation[r, c]), r, c))

        dr = [-1, -1, -1,  0,  0,  1,  1,  1]
        dc = [-1,  0,  1, -1,  1, -1,  0,  1]

        while pq:
            elev, r, c = heapq.heappop(pq)
            for k in range(8):
                nr, nc = r + dr[k], c + dc[k]
                if 0 <= nr < nrows and 0 <= nc < ncols:
                    if filled[nr, nc] == np.inf:
                        filled[nr, nc] = max(elevation[nr, nc], elev + 1e-5)
                        heapq.heappush(pq, (float(filled[nr, nc]), nr, nc))

        return filled

    def _compute_d8_flow_directions(self, filled: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Computes D8 flow directions based on steepest gradient descent.
        """
        nrows, ncols = self.nrows, self.ncols
        flow_dir = np.full((nrows, ncols), -1, dtype=np.int32)
        downstream_target = np.full((nrows, ncols, 2), -1, dtype=np.int32)

        dr = [-1, -1, -1,  0,  0,  1,  1,  1]
        dc = [-1,  0,  1, -1,  1, -1,  0,  1]
        dist = [math.sqrt(2) * self.cell_size, self.cell_size, math.sqrt(2) * self.cell_size,
                self.cell_size, self.cell_size,
                math.sqrt(2) * self.cell_size, self.cell_size, math.sqrt(2) * self.cell_size]

        for r in range(nrows):
            for c in range(ncols):
                best_slope = -1.0
                best_k = -1
                for k in range(8):
                    nr, nc = r + dr[k], c + dc[k]
                    if 0 <= nr < nrows and 0 <= nc < ncols:
                        drop = (filled[r, c] - filled[nr, nc]) / dist[k]
                        if drop > best_slope:
                            best_slope = drop
                            best_k = k

                flow_dir[r, c] = best_k
                if best_k != -1:
                    downstream_target[r, c] = [r + dr[best_k], c + dc[best_k]]

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
        Handles both stream channels and inland natural depression retention basins.
        """
        nrows, ncols = self.nrows, self.ncols
        outlet_row = max(0, min(nrows - 1, outlet_row))
        outlet_col = max(0, min(ncols - 1, outlet_col))

        # Check in a small 3x3 window if there is a higher accumulation cell or stream channel
        best_r, best_c = outlet_row, outlet_col
        max_acc = self.flow_acc[outlet_row, outlet_col]
        for dr in range(-2, 3):
            for dc in range(-2, 3):
                nr, nc = outlet_row + dr, outlet_col + dc
                if 0 <= nr < nrows and 0 <= nc < ncols:
                    if self.flow_acc[nr, nc] > max_acc:
                        max_acc = self.flow_acc[nr, nc]
                        best_r, best_c = nr, nc

        # Use the local flow confluence if nearby accumulation is significantly higher
        if max_acc >= 50 and self.flow_acc[outlet_row, outlet_col] < 10:
            target_r, target_c = best_r, best_c
        else:
            target_r, target_c = outlet_row, outlet_col

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
        queue = deque([(target_r, target_c)])
        catchment_mask[target_r, target_c] = True

        while queue:
            curr = queue.popleft()
            if curr in upstream_map:
                for up_cell in upstream_map[curr]:
                    ur, uc = up_cell
                    if not catchment_mask[ur, uc]:
                        catchment_mask[ur, uc] = True
                        queue.append((ur, uc))

        # If the point is in a natural topographic bowl (retention amphitheater) where filled DEM accumulation is small,
        # also capture the surrounding inward-sloping bowl basin
        if np.sum(catchment_mask) * self.cell_area_m2 < 30000:
            elev = self.dem.elevation
            outlet_elev = elev[outlet_row, outlet_col]
            for dr in range(-20, 21):
                for dc in range(-20, 21):
                    nr, nc = outlet_row + dr, outlet_col + dc
                    if 0 <= nr < nrows and 0 <= nc < ncols:
                        dist_m = math.sqrt(dr**2 + dc**2) * self.cell_size
                        # Include inward sloping cells in amphitheater up to rim (within 220m and <= outlet + 12m)
                        if dist_m <= 220.0 and elev[nr, nc] <= (outlet_elev + 13.0):
                            catchment_mask[nr, nc] = True

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
            if len(line) < 4:
                continue
            ring_coords = []
            for px, py in line:
                grid_c = px - 1.0
                grid_r = py - 1.0
                lon, lat = self.dem.grid_to_geo(grid_r, grid_c)
                ring_coords.append([round(lon, 6), round(lat, 6)])

            if ring_coords[0] != ring_coords[-1]:
                ring_coords.append(ring_coords[0])

            polygon_geometries.append(ring_coords)

        if not polygon_geometries:
            # Fallback circle around outlet
            r_deg = (math.sqrt(area_m2 / math.pi) / 111320.0)
            pts = []
            for angle in range(0, 361, 15):
                rad = math.radians(angle)
                pts.append([
                    round(outlet_lon + r_deg * math.cos(rad) / math.cos(math.radians(outlet_lat)), 6),
                    round(outlet_lat + r_deg * math.sin(rad), 6)
                ])
            polygon_geometries = [pts]

        geom_type = "Polygon" if len(polygon_geometries) == 1 else "MultiPolygon"
        coords = polygon_geometries if len(polygon_geometries) == 1 else [[ring] for ring in polygon_geometries]

        return {
            "type": "Feature",
            "properties": {
                "area_sq_meters": round(area_m2, 2),
                "area_hectares": round(area_m2 / 10000.0, 3),
                "area_sq_km": round(area_m2 / 1e6, 4),
                "outlet_lat": round(outlet_lat, 6),
                "outlet_lon": round(outlet_lon, 6)
            },
            "geometry": {
                "type": geom_type,
                "coordinates": coords
            }
        }
