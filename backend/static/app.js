// Village Pond Planning System - Interactive Map & Dashboard
// Standalone Self-Contained Implementation

let map;
let selectedFile = null;
let currentMode = "auto"; // "auto" or "manual"
let manualPin = null;
let currentResults = null;

// Layer Groups
let contourLayerGroup;
let catchmentLayerGroup;
let markerLayerGroup;

// Helper to safely set text content if element exists
function setElText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
}

function getElevationColor(elev, minElev, maxElev) {
    if (maxElev === minElev) return "#f59e0b";
    const ratio = Math.max(0, Math.min(1, (elev - minElev) / (maxElev - minElev)));
    const hue = 45 - ratio * 35;
    return `hsl(${hue}, 90%, 55%)`;
}

document.addEventListener("DOMContentLoaded", () => {
    initMap();
    initEventListeners();
});

function initMap() {
    const mapEl = document.getElementById("map");
    mapEl.style.width = "100%";
    mapEl.style.height = "100%";
    mapEl.style.minHeight = "400px";

    map = L.map("map", {
        center: [21.251, 81.297],
        zoom: 14,
        zoomControl: true
    });

    // Base tile layers
    const osmLayer = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "&copy; OpenStreetMap",
        maxZoom: 19,
        crossOrigin: true
    }).addTo(map);

    const satelliteLayer = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
        attribution: "&copy; Esri World Imagery",
        maxZoom: 19,
        crossOrigin: true
    });

    const cartoDark = L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
        attribution: "&copy; CARTO",
        maxZoom: 19,
        crossOrigin: true
    });

    // Layer switcher control
    L.control.layers({
        "OpenStreetMap": osmLayer,
        "🛰️ Satellite Imagery": satelliteLayer,
        "Dark Canvas": cartoDark
    }, null, { position: "topright" }).addTo(map);

    contourLayerGroup = L.layerGroup().addTo(map);
    catchmentLayerGroup = L.layerGroup().addTo(map);
    markerLayerGroup = L.layerGroup().addTo(map);

    map.on("click", (e) => {
        if (currentMode === "manual" || selectedFile) {
            handleManualMapClick(e.latlng.lat, e.latlng.lng);
        }
    });

    // Force multiple resize events to ensure Leaflet computes container size
    setTimeout(() => map.invalidateSize(), 100);
    setTimeout(() => map.invalidateSize(), 500);
    setTimeout(() => map.invalidateSize(), 1500);
}

function initEventListeners() {
    const dropZone = document.getElementById("drop-zone");
    const fileInput = document.getElementById("file-input");
    const analyzeBtn = document.getElementById("analyze-btn");
    const loadSampleBtn = document.getElementById("load-sample-btn");
    const modeAutoBtn = document.getElementById("mode-auto-btn");
    const modeManualBtn = document.getElementById("mode-manual-btn");
    const closeResultsBtn = document.getElementById("close-results-btn");

    if (dropZone && fileInput) {
        dropZone.addEventListener("click", () => fileInput.click());
        fileInput.addEventListener("change", (e) => {
            if (e.target.files.length > 0) setFile(e.target.files[0]);
        });
        dropZone.addEventListener("dragover", (e) => e.preventDefault());
        dropZone.addEventListener("drop", (e) => {
            e.preventDefault();
            if (e.dataTransfer.files.length > 0) setFile(e.dataTransfer.files[0]);
        });
    }

    if (modeAutoBtn) modeAutoBtn.addEventListener("click", () => setMode("auto"));
    if (modeManualBtn) modeManualBtn.addEventListener("click", () => setMode("manual"));
    if (analyzeBtn) analyzeBtn.addEventListener("click", () => runAnalysis());
    if (loadSampleBtn) loadSampleBtn.addEventListener("click", () => loadSampleFile());

    if (closeResultsBtn) {
        closeResultsBtn.addEventListener("click", () => {
            const panel = document.getElementById("results-panel");
            if (panel) panel.classList.add("hidden");
        });
    }
}

function setFile(file) {
    selectedFile = file;
    setElText("file-name-label", `Loaded: ${file.name}`);
}

function setMode(mode) {
    currentMode = mode;
    const autoBtn = document.getElementById("mode-auto-btn");
    const manualBtn = document.getElementById("mode-manual-btn");
    const tip = document.getElementById("manual-tip");

    if (mode === "auto") {
        if (autoBtn) autoBtn.classList.add("active");
        if (manualBtn) manualBtn.classList.remove("active");
        if (tip) tip.style.display = "none";
    } else {
        if (manualBtn) manualBtn.classList.add("active");
        if (autoBtn) autoBtn.classList.remove("active");
        if (tip) tip.style.display = "block";
    }
}

async function loadSampleFile() {
    showLoading(true, "Loading sample contour map (contours_1m.kml)...");
    try {
        let resp = await fetch("/contours_1m.kml");
        if (!resp.ok) resp = await fetch("/static/contours_1m.kml");
        if (!resp.ok) throw new Error("Could not load sample file.");

        const blob = await resp.blob();
        const file = new File([blob], "contours_1m.kml", { type: "application/vnd.google-earth.kml+xml" });
        setFile(file);
        showLoading(false);
        runAnalysis();
    } catch (err) {
        showLoading(false);
        alert("Please drag and drop contours_1m.kml into the upload box.");
    }
}

function showLoading(show, text = "Processing DEM & Hydrology...") {
    const overlay = document.getElementById("loading-overlay");
    const label = document.getElementById("loading-text");
    if (label) label.textContent = text;
    if (overlay) {
        if (show) overlay.classList.remove("hidden");
        else overlay.classList.add("hidden");
    }
}

async function runAnalysis() {
    if (!selectedFile) {
        alert("Please select or upload a KML / KMZ contour map first.");
        return;
    }

    showLoading(true, "Parsing contours & interpolating DEM...");

    const formData = new FormData();
    formData.append("contour_map", selectedFile);
    formData.append("file", selectedFile);
    
    const landEl = document.getElementById("land-cover-select");
    if (landEl) formData.append("land_cover", landEl.value);

    const cEl = document.getElementById("runoff-override");
    if (cEl && cEl.value) formData.append("runoff_coeff", cEl.value);

    const rEl = document.getElementById("rainfall-override");
    if (rEl && rEl.value) formData.append("rainfall_mm", rEl.value);

    if (currentMode === "manual" && manualPin) {
        formData.append("pond_lat", manualPin.lat);
        formData.append("pond_lon", manualPin.lng);
    }

    try {
        const response = await fetch("/api/v1/processAll", {
            method: "POST",
            body: formData
        });

        if (!response.ok) {
            const errData = await response.json().catch(() => ({}));
            throw new Error(errData.detail || "Analysis failed");
        }

        const data = await response.json();
        currentResults = data;
        renderResultsOnMap(data);
        populateResultsSidebar(data);
    } catch (error) {
        alert(`Error running analysis: ${error.message}`);
    } finally {
        showLoading(false);
        setTimeout(() => map.invalidateSize(), 200);
    }
}

async function handleManualMapClick(lat, lng) {
    if (!selectedFile) return;

    manualPin = { lat, lng };
    setMode("manual");

    showLoading(true, `Delineating catchment for (${lat.toFixed(4)}, ${lng.toFixed(4)})...`);

    const formData = new FormData();
    formData.append("contour_map", selectedFile);
    formData.append("file", selectedFile);
    formData.append("pond_lat", lat);
    formData.append("pond_lon", lng);

    const landEl = document.getElementById("land-cover-select");
    if (landEl) formData.append("land_cover", landEl.value);

    const cEl = document.getElementById("runoff-override");
    if (cEl && cEl.value) formData.append("runoff_coeff", cEl.value);

    const rEl = document.getElementById("rainfall-override");
    if (rEl && rEl.value) formData.append("rainfall_mm", rEl.value);

    try {
        const response = await fetch("/api/v1/findCatchment", {
            method: "POST",
            body: formData
        });

        if (!response.ok) {
            const errData = await response.json().catch(() => ({}));
            throw new Error(errData.detail || "Catchment delineation failed");
        }

        const catchmentData = await response.json();
        renderCatchmentOnly(catchmentData);
        populateCatchmentSidebar(catchmentData);
    } catch (error) {
        alert(`Error delineating catchment: ${error.message}`);
    } finally {
        showLoading(false);
        setTimeout(() => map.invalidateSize(), 200);
    }
}

function renderResultsOnMap(data) {
    try {
        contourLayerGroup.clearLayers();
        catchmentLayerGroup.clearLayers();
        markerLayerGroup.clearLayers();

        const t = data.terrain_analysis;

        // Force map resize before rendering
        map.invalidateSize();

        if (t.contours_geojson) {
            const minE = t.elevation_stats.min_m;
            const maxE = t.elevation_stats.max_m;

            const contourLayer = L.geoJSON(t.contours_geojson, {
                style: (feature) => ({
                    color: getElevationColor(feature.properties.elevation, minE, maxE),
                    weight: 1.5,
                    opacity: 0.85
                })
            }).addTo(contourLayerGroup);

            map.fitBounds(contourLayer.getBounds(), { padding: [30, 30] });
            console.log("Contours rendered:", t.contours_geojson.features ? t.contours_geojson.features.length : 0, "features");
        }

        // If no contours, center on known region
        if (!t.contours_geojson) {
            map.setView([t.elevation_stats ? 21.251 : 21.251, 81.297], 14);
        }

    if (data.catchment_geojson) {
        const catchmentLayer = L.geoJSON(data.catchment_geojson, {
            style: {
                color: "#38bdf8",
                weight: 2.5,
                fillColor: "#0284c7",
                fillOpacity: 0.35,
                dashArray: "4, 4"
            }
        }).addTo(catchmentLayerGroup);

        map.fitBounds(catchmentLayer.getBounds(), { padding: [40, 40] });
    }

    if (t.recommended_pond_sites) {
        t.recommended_pond_sites.forEach((site) => {
            const isPrimary = site.rank === 1;
            const customIcon = L.divIcon({
                html: `<div class="custom-pond-marker ${isPrimary ? 'primary' : 'secondary'}">${site.rank}</div>`,
                className: "custom-pond-icon",
                iconSize: [28, 28],
                iconAnchor: [14, 14]
            });

            const marker = L.marker([site.lat, site.lon], { icon: customIcon }).addTo(markerLayerGroup);
            marker.bindPopup(`
                <div style="font-size: 12px; line-height: 1.5;">
                    <p style="font-weight: bold; color: var(--primary-emerald);">Option #${site.rank}: Optimal Pond Site</p>
                    <p><strong>Coords:</strong> ${site.lat.toFixed(5)}, ${site.lon.toFixed(5)}</p>
                    <p><strong>Score:</strong> ${site.suitability_score}/100</p>
                    <p><strong>Elevation:</strong> ${site.elevation_m} m | <strong>Slope:</strong> ${site.slope_pct}%</p>
                    <p><strong>Catchment:</strong> ${(site.estimated_catchment_m2 / 10000).toFixed(1)} ha</p>
                </div>
            `);
            marker.on("click", () => handleManualMapClick(site.lat, site.lon));
        });

        // Render Candidates Sidebar List
        const container = document.getElementById("candidate-container");
        const list = document.getElementById("candidate-list");
        if (container && list) {
            list.innerHTML = "";
            container.classList.remove("hidden");

            t.recommended_pond_sites.forEach((site) => {
                const card = document.createElement("div");
                card.className = `candidate-card ${site.rank === 1 ? 'primary' : ''}`;
                card.innerHTML = `
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                        <span style="font-weight: 700; color: #ffffff;">#${site.rank} Pond Site (${site.suitability_score}/100)</span>
                        <span style="font-size: 10px; background: #334155; padding: 2px 6px; border-radius: 4px;">${site.slope_pct}% slope</span>
                    </div>
                    <p style="font-size: 11px; color: var(--text-secondary);">Catchment: ${(site.estimated_catchment_m2 / 10000).toFixed(1)} ha | Elev: ${site.elevation_m}m</p>
                `;
                card.addEventListener("click", () => {
                    map.flyTo([site.lat, site.lon], 16);
                    handleManualMapClick(site.lat, site.lon);
                });
                list.appendChild(card);
            });
        }
    }

    // Force final resize after all layers added
    setTimeout(() => map.invalidateSize(), 200);

    } catch (err) {
        console.error("renderResultsOnMap error:", err);
        alert("Map rendering error: " + err.message);
    }
}

function renderCatchmentOnly(data) {
    catchmentLayerGroup.clearLayers();

    if (data.catchment_geojson) {
        const catchmentLayer = L.geoJSON(data.catchment_geojson, {
            style: {
                color: "#38bdf8",
                weight: 2.5,
                fillColor: "#0284c7",
                fillOpacity: 0.35,
                dashArray: "4, 4"
            }
        }).addTo(catchmentLayerGroup);

        map.fitBounds(catchmentLayer.getBounds(), { padding: [40, 40] });
    }

    const loc = data.pond_location;
    const marker = L.marker([loc.lat, loc.lon], {
        icon: L.divIcon({
            html: `<div class="custom-pond-marker primary" style="background: #f59e0b;">📍</div>`,
            className: "custom-pond-icon",
            iconSize: [28, 28],
            iconAnchor: [14, 14]
        })
    }).addTo(catchmentLayerGroup);

    marker.bindPopup(`
        <div style="font-size: 12px; line-height: 1.5;">
            <p style="font-weight: bold; color: #f59e0b;">Selected Pond Outlet</p>
            <p><strong>Coords:</strong> ${loc.lat.toFixed(5)}, ${loc.lon.toFixed(5)}</p>
            <p><strong>Catchment:</strong> ${data.catchment_area.hectares} ha</p>
        </div>
    `).openPopup();
}

function populateResultsSidebar(data) {
    const panel = document.getElementById("results-panel");
    if (panel) panel.classList.remove("hidden");

    const c = data.catchment_area;
    const d = data.pond_design;
    const h = data.hydrology;
    const loc = data.selected_pond_location;
    const t = data.terrain_analysis;

    setElText("res-mode-label", loc.selection_mode || "Optimal Pond Site");
    setElText("stat-catchment-ha", `${c.hectares.toLocaleString()} ha`);
    setElText("stat-catchment-m2", `${Math.round(c.sq_meters).toLocaleString()} m² (${c.sq_km} km²)`);

    setElText("stat-runoff-vol", `${Math.round(data.annual_runoff_volume_m3).toLocaleString()} m³`);
    setElText("stat-rainfall-source", `R = ${h.annual_rainfall_mm} mm (C = ${h.runoff_coefficient})`);

    setElText("spec-storage", `${d.target_storage_m3.toLocaleString()} m³`);
    setElText("spec-depth", `${d.recommended_depth_m} m (Water: ${d.water_depth_m}m + Freeboard: ${d.freeboard_m}m)`);
    setElText("spec-dims", `${d.length_m} m (L) × ${d.width_m} m (W)`);
    setElText("spec-surf-area", `${d.top_surface_area_m2.toLocaleString()} m²`);
    setElText("spec-base-area", `${d.bottom_base_area_m2.toLocaleString()} m²`);
    setElText("spec-excavation", `${d.excavation_volume_m3.toLocaleString()} m³`);

    setElText("stat-outlet-coords", `${loc.lat.toFixed(5)}, ${loc.lon.toFixed(5)}`);
    setElText("stat-outlet-elev", `${loc.elevation_m} m`);
    setElText("stat-outlet-slope", `${loc.slope_pct}%`);
    setElText("stat-relief", `${t.elevation_stats.relief_m} m (${t.elevation_stats.min_m}m - ${t.elevation_stats.max_m}m)`);
    setElText("stat-flat-pct", `${t.slope_stats.flat_area_pct}%`);
}

function populateCatchmentSidebar(data) {
    const panel = document.getElementById("results-panel");
    if (panel) panel.classList.remove("hidden");

    const c = data.catchment_area;
    const d = data.pond_design;
    const h = data.hydrology;
    const loc = data.pond_location;

    setElText("res-mode-label", loc.selection_mode || "Manual coordinate selection");
    setElText("stat-catchment-ha", `${c.hectares.toLocaleString()} ha`);
    setElText("stat-catchment-m2", `${Math.round(c.sq_meters).toLocaleString()} m² (${c.sq_km} km²)`);

    setElText("stat-runoff-vol", `${Math.round(data.annual_runoff_volume_m3).toLocaleString()} m³`);
    setElText("stat-rainfall-source", `R = ${h.annual_rainfall_mm} mm (C = ${h.runoff_coefficient})`);

    setElText("spec-storage", `${d.target_storage_m3.toLocaleString()} m³`);
    setElText("spec-depth", `${d.recommended_depth_m} m (Water: ${d.water_depth_m}m + Freeboard: ${d.freeboard_m}m)`);
    setElText("spec-dims", `${d.length_m} m × ${d.width_m} m`);
    setElText("spec-surf-area", `${d.top_surface_area_m2.toLocaleString()} m²`);
    setElText("spec-base-area", `${d.bottom_base_area_m2.toLocaleString()} m²`);
    setElText("spec-excavation", `${d.excavation_volume_m3.toLocaleString()} m³`);

    setElText("stat-outlet-coords", `${loc.lat.toFixed(5)}, ${loc.lon.toFixed(5)}`);
    setElText("stat-outlet-elev", `${loc.elevation_m} m`);
    setElText("stat-outlet-slope", `${loc.slope_pct}%`);

    // Use cached terrain stats from initial processAll run
    if (currentResults && currentResults.terrain_analysis) {
        const t = currentResults.terrain_analysis;
        setElText("stat-relief", `${t.elevation_stats.relief_m} m (${t.elevation_stats.min_m}m - ${t.elevation_stats.max_m}m)`);
        setElText("stat-flat-pct", `${t.slope_stats.flat_area_pct}%`);
    }
}
