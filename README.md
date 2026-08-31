# AI-Based Village Pond Planning System: Terrain & Catchment Engine

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An automated backend geospatial API and interactive dashboard for village pond planning. Accepts terrain contour maps (in **KML** & **KMZ** format), reconstructs continuous Digital Elevation Models (DEM), computes slope and D8 hydrological routing matrices, discovers optimal pond site depressions, delineates upstream catchment watersheds, and sizes trapezoidal farm ponds using the Rational Method.

---

## Key Features

- **Dynamic KML & KMZ Parser:** Extracts 2D/3D contour isolines and elevation tags from XML without hard-coded assumptions or coordinate bounds.
- **Metric Projection & DEM Interpolation:** Dynamically projects WGS84 geographic coordinates to Cartesian metric meters and reconstructs regular elevation rasters using Delaunay TIN barycentric interpolation.
- **Priority-Flood Hydrology Engine:** Resolves sinks and digital pits while modeling D8 flow direction and linear $O(N)$ topological flow accumulation.
- **Dual-Mode Watershed Delineation:** Supports fully automatic optimal site selection or manual map-click coordinate specification.
- **Land-Cover Aware Runoff Modeling:** Built-in lookup table ($C=0.30$ to $0.70$), multi-source rainfall priority fallback chain (Open-Meteo $\to$ NASA POWER $\to$ regional baseline), and prismoidal pond geometry sizing.
- **Interactive Web Dashboard:** Built-in Leaflet.js map with satellite layer toggle, elevation-colored contours, and real-time catchment polygon rendering.

---

## Quick Start

### 1. Installation
```bash
git clone https://github.com/Venkat-1905/pond-planning-system.git
cd pond-planning-system

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Run the Backend API Server
```bash
uvicorn backend.app:app --host 0.0.0.0 --port 5000 --reload
```
- **Web Dashboard:** [http://localhost:5233/](http://localhost:5233/)
- **Interactive OpenAPI Console:** [http://localhost:5233/docs](http://localhost:5233/docs)

### 3. Run CLI Sample Demonstration
```bash
python scripts/test_sample_contour.py
```

### 4. Run Automated Test Suite
```bash
pytest backend/tests/ -v
```

---

## API Endpoints Overview

| Route | Method | Description |
| :--- | :--- | :--- |
| `/analyzeContour` | `POST` | Uploads KML/KMZ; returns DEM stats, slope distribution, and top 3 candidate pond sites. |
| `/findCatchment` | `POST` | Uploads KML/KMZ + optional `pond_lat`/`pond_lon`; returns catchment GeoJSON polygon & pond sizing. |
| `/pond/analyze` | `POST` | JSON endpoint calculating Rational runoff and pond dimensions for pre-computed areas. |
| `/processAll` | `POST` | Unified pipeline endpoint returning full terrain analysis, candidates, and delineated watershed. |
| `/health` | `GET` | Service uptime and status check. |

---

## Project Structure
```
pond/
├── backend/
│   ├── app.py                     # FastAPI REST API & static file mount
│   ├── core/
│   │   ├── __init__.py
│   │   ├── kml_parser.py          # Dynamic KML/KMZ parser & metric projection
│   │   ├── dem_interpolator.py    # DEM grid reconstruction & slope analysis
│   │   ├── hydrology.py           # D8 flow direction, accumulation & watershed BFS
│   │   ├── pond_optimizer.py      # Site scoring, rainfall fallback & pond sizing
│   │   └── schemas.py             # Pydantic schemas with strict validation
│   ├── static/                    # Leaflet.js interactive web dashboard
│   │   ├── index.html
│   │   ├── app.js
│   │   └── style.css
│   └── tests/
│       ├── test_kml_parser.py
│       ├── test_hydrology.py
│       └── test_api.py
├── scripts/
│   ├── deploy.sh                  # One-command remote cluster deployment script
│   └── test_sample_contour.py     # CLI demonstration script
├── contours_1m.kml                 # Sample contour dataset
├── requirements.txt               # Dependencies
├── README.md                      # Quickstart and overview
└── REPORT.md                      # Technical assignment report
```

---

## Evaluation & Deployment

To deploy to remote cluster node `stu9_sys1` on port `5233` (container port `5000`) (password: `venkat19@`):
```bash
SSH_PORT=2233 PORT=5000 ./scripts/deploy.sh
```

---

## Author
- **Name:** Venkat
- **Roll No:** 12341070
- **Course:** Computer System Design (CSD)
