// Village Pond Planning System - Interactive Map & Dashboard

let map;
let selectedFile = null;
let currentMode = "auto"; // "auto" or "manual"
let manualPin = null;
let currentResults = null;

// Layer Groups
let contourLayerGroup;
let catchmentLayerGroup;
let markerLayerGroup;

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
    map = L.map("map", {
        center: [21.251, 81.297],
        zoom: 14,
        zoomControl: true
    });

    const osmLayer = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "&copy; OpenStreetMap contributors",
        maxZoom: 19
    });

    const satelliteLayer = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
        attribution: "&copy; Esri, Maxar, Earthstar Geographics",
        maxZoom: 19
    });

    const cartoDark = L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
        attribution: "&copy; CARTO",
        maxZoom: 19
    }).addTo(map);

    L.control.layers({
        "Dark Canvas": cartoDark,
        "Satellite Imagery": satelliteLayer,
        "OpenStreetMap": osmLayer
    }, null, { position: "topright" }).addTo(map);

    contourLayerGroup = L.layerGroup().addTo(map);
    catchmentLayerGroup = L.layerGroup().addTo(map);
    markerLayerGroup = L.layerGroup().addTo(map);

    map.on("click", (e) => {
        if (currentMode === "manual" || selectedFile) {
            handleManualMapClick(e.latlng.lat, e.latlng.lng);
        }
    });
}

function initEventListeners() {
    const dropZone = document.getElementById("drop-zone");
    const fileInput = document.getElementById("file-input");
    const analyzeBtn = document.getElementById("analyze-btn");
    const loadSampleBtn = document.getElementById("load-sample-btn");
    const modeAutoBtn = document.getElementById("mode-auto-btn");
    const modeManualBtn = document.getElementById("mode-manual-btn");
    const closeResultsBtn = document.getElementById("close-results-btn");
    const exportJsonBtn = document.getElementById("export-json-btn");

    dropZone.addEventListener("click", () => fileInput.click());

    fileInput.addEventListener("change", (e) => {
        if (e.target.files.length > 0) {
            setFile(e.target.files[0]);
        }
    });

    dropZone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropZone.classList.add("border-emerald-500", "bg-slate-800");
    });

    dropZone.addEventListener("dragleave", () => {
        dropZone.classList.remove("border-emerald-500", "bg-slate-800");
    });

    dropZone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropZone.classList.remove("border-emerald-500", "bg-slate-800");
        if (e.dataTransfer.files.length > 0) {
            setFile(e.dataTransfer.files[0]);
        }
    });

    modeAutoBtn.addEventListener("click", () => setMode("auto"));
    modeManualBtn.addEventListener("click", () => setMode("manual"));

    analyzeBtn.addEventListener("click", () => runAnalysis());
    loadSampleBtn.addEventListener("click", () => loadSampleFile());

    closeResultsBtn.addEventListener("click", () => {
        document.getElementById("results-panel").classList.add("hidden");
    });

    exportJsonBtn.addEventListener("click", () => exportGeoJSON());
}

function setFile(file) {
    selectedFile = file;
    document.getElementById("file-name-label").textContent = file.name;
    document.getElementById("file-name-label").classList.add("text-emerald-400", "font-semibold");
    document.getElementById("status-indicator").textContent = `Loaded: ${file.name}`;
}

function setMode(mode) {
    currentMode = mode;
    const autoBtn = document.getElementById("mode-auto-btn");
    const manualBtn = document.getElementById("mode-manual-btn");
    const manualTip = document.getElementById("manual-tip");

    if (mode === "auto") {
        autoBtn.className = "px-2.5 py-1.5 rounded-lg text-xs font-medium bg-emerald-600 text-white border border-emerald-500 shadow-sm transition flex items-center justify-center gap-1";
        manualBtn.className = "px-2.5 py-1.5 rounded-lg text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition flex items-center justify-center gap-1";
        manualTip.classList.add("hidden");
    } else {
        manualBtn.className = "px-2.5 py-1.5 rounded-lg text-xs font-medium bg-emerald-600 text-white border border-emerald-500 shadow-sm transition flex items-center justify-center gap-1";
        autoBtn.className = "px-2.5 py-1.5 rounded-lg text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition flex items-center justify-center gap-1";
        manualTip.classList.remove("hidden");
    }
}

async function loadSampleFile() {
    showLoading(true, "Loading sample contour map (contours_1m.kml)...");
    try {
        let resp = await fetch("/contours_1m.kml");
        if (!resp.ok) {
            resp = await fetch("/static/contours_1m.kml");
        }
        if (!resp.ok) {
            throw new Error("Could not fetch sample map file.");
        }
        const blob = await resp.blob();
        const file = new File([blob], "contours_1m.kml", { type: "application/vnd.google-earth.kml+xml" });
        setFile(file);
        showLoading(false);
        runAnalysis();
    } catch (err) {
        showLoading(false);
        alert("Please drag and drop the contours_1m.kml file from your computer into the upload box.");
    }
}

function showLoading(show, text = "Processing DEM & Hydrology...") {
    const overlay = document.getElementById("loading-overlay");
    const label = document.getElementById("loading-text");
    if (show) {
        label.textContent = text;
        overlay.classList.remove("hidden");
    } else {
        overlay.classList.add("hidden");
    }
}

async function runAnalysis() {
    if (!selectedFile) {
        alert("Please select or upload a KML / KMZ contour map first.");
        return;
    }

    showLoading(true, "Parsing contours & interpolating DEM...");

    const formData = new FormData();
    formData.append("file", selectedFile);
    formData.append("land_cover", document.getElementById("land-cover-select").value);

    const cVal = document.getElementById("c-override").value;
    if (cVal) formData.append("runoff_coeff", cVal);

    const rVal = document.getElementById("rainfall-override").value;
    if (rVal) formData.append("rainfall_mm", rVal);

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
            const errData = await response.json();
            throw new Error(errData.detail || "Analysis failed");
        }

        const data = await response.json();
        currentResults = data;
        renderResultsOnMap(data);
        populateResultsSidebar(data);
        showLoading(false);
    } catch (error) {
        showLoading(false);
        alert(`Error running analysis: ${error.message}`);
    }
}

async function handleManualMapClick(lat, lng) {
    if (!selectedFile) return;

    manualPin = { lat, lng };
    setMode("manual");

    showLoading(true, `Delineating catchment for (${lat.toFixed(4)}, ${lng.toFixed(4)})...`);

    const formData = new FormData();
    formData.append("file", selectedFile);
    formData.append("pond_lat", lat);
    formData.append("pond_lon", lng);
    formData.append("land_cover", document.getElementById("land-cover-select").value);

    const cVal = document.getElementById("c-override").value;
    if (cVal) formData.append("runoff_coeff", cVal);

    const rVal = document.getElementById("rainfall-override").value;
    if (rVal) formData.append("rainfall_mm", rVal);

    try {
        const response = await fetch("/api/v1/findCatchment", {
            method: "POST",
            body: formData
        });

        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.detail || "Catchment delineation failed");
        }

        const catchmentData = await response.json();
        renderCatchmentOnly(catchmentData);
        populateCatchmentSidebar(catchmentData);
        showLoading(false);
    } catch (error) {
        showLoading(false);
        alert(`Error delineating catchment: ${error.message}`);
    }
}

function renderResultsOnMap(data) {
    contourLayerGroup.clearLayers();
    catchmentLayerGroup.clearLayers();
    markerLayerGroup.clearLayers();

    const t = data.terrain_analysis;

    if (t.contours_geojson && t.contours_geojson.features) {
        const minE = t.elevation_stats.min_m;
        const maxE = t.elevation_stats.max_m;

        L.geoJSON(t.contours_geojson, {
            style: (feature) => ({
                color: getElevationColor(feature.properties.elevation, minE, maxE),
                weight: 1.2,
                opacity: 0.75
            }),
            onEachFeature: (feature, layer) => {
                layer.bindTooltip(`Elev: ${feature.properties.elevation} m`, { sticky: true, className: "text-xs" });
            }
        }).addTo(contourLayerGroup);
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

        map.fitBounds(catchmentLayer.getBounds(), { padding: [30, 30] });
    }

    t.recommended_pond_sites.forEach((site) => {
        const isPrimary = site.rank === 1;
        const iconHtml = `<div class="custom-pond-marker ${isPrimary ? "primary" : "secondary"}">${site.rank}</div>`;

        const customIcon = L.divIcon({
            html: iconHtml,
            className: "custom-pond-icon",
            iconSize: [28, 28],
            iconAnchor: [14, 14]
        });

        const marker = L.marker([site.lat, site.lon], { icon: customIcon }).addTo(markerLayerGroup);
        marker.bindPopup(`
            <div class="text-xs space-y-1.5 p-1">
                <p class="font-bold text-emerald-400 text-sm">Option #${site.rank}: Optimal Pond Site</p>
                <p class="text-slate-300"><strong>Coords:</strong> ${site.lat.toFixed(5)}, ${site.lon.toFixed(5)}</p>
                <p class="text-slate-300"><strong>Score:</strong> ${site.suitability_score}/100</p>
                <p class="text-slate-300"><strong>Elevation:</strong> ${site.elevation_m} m | <strong>Slope:</strong> ${site.slope_pct}%</p>
                <p class="text-slate-300"><strong>Catchment Area:</strong> ${(site.estimated_catchment_m2 / 10000).toFixed(1)} ha</p>
            </div>
        `);
        marker.on("click", () => {
            handleManualMapClick(site.lat, site.lon);
        });
    });

    const container = document.getElementById("candidate-container");
    const list = document.getElementById("candidate-list");
    list.innerHTML = "";
    container.classList.remove("hidden");

    t.recommended_pond_sites.forEach((site) => {
        const card = document.createElement("div");
        card.className = `candidate-card ${site.rank === 1 ? "primary" : ""}`;
        card.innerHTML = `
            <div class="flex justify-between items-center mb-1">
                <span class="font-bold text-white">#${site.rank} Pond Site (${site.suitability_score}/100)</span>
                <span class="text-[10px] px-1.5 py-0.5 rounded bg-slate-700 text-slate-300">${site.slope_pct}% slope</span>
            </div>
            <p class="text-[11px] text-slate-400">Catchment: ${(site.estimated_catchment_m2 / 10000).toFixed(1)} ha | Elev: ${site.elevation_m}m</p>
        `;
        card.addEventListener("click", () => {
            map.flyTo([site.lat, site.lon], 16);
            handleManualMapClick(site.lat, site.lon);
        });
        list.appendChild(card);
    });
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

        map.fitBounds(catchmentLayer.getBounds(), { padding: [30, 30] });
    }

    const loc = data.pond_location;
    const iconHtml = `
        <div class="relative flex items-center justify-center">
            <div class="pulse-ring"></div>
            <div class="w-7 h-7 rounded-full bg-amber-500 border-2 border-white text-slate-950 flex items-center justify-center font-bold text-xs shadow-lg">
                <i class="fa-solid fa-location-pin"></i>
            </div>
        </div>
    `;
    const marker = L.marker([loc.lat, loc.lon], {
        icon: L.divIcon({ html: iconHtml, className: "custom-pond-icon", iconSize: [28, 28], iconAnchor: [14, 14] })
    }).addTo(catchmentLayerGroup);

    marker.bindPopup(`
        <div class="text-xs space-y-1 p-1">
            <p class="font-bold text-amber-400">Selected Pond Outlet</p>
            <p>Coords: ${loc.lat.toFixed(5)}, ${loc.lon.toFixed(5)}</p>
            <p>Catchment: ${data.catchment_area.hectares} ha</p>
        </div>
    `).openPopup();
}

function populateResultsSidebar(data) {
    const panel = document.getElementById("results-panel");
    panel.classList.remove("hidden");

    const c = data.catchment_area;
    const d = data.pond_design;
    const h = data.hydrology;
    const loc = data.selected_pond_location;
    const t = data.terrain_analysis;

    document.getElementById("report-mode").textContent = loc.selection_mode || "Optimal Pond Site";
    document.getElementById("res-catchment-ha").textContent = `${c.hectares.toLocaleString()} ha`;
    document.getElementById("res-catchment-m2").textContent = `${Math.round(c.sq_meters).toLocaleString()} m² (${c.sq_km} km²)`;

    document.getElementById("res-runoff-m3").textContent = `${Math.round(data.annual_runoff_volume_m3).toLocaleString()} m³`;
    document.getElementById("res-rainfall-source").textContent = `R = ${h.annual_rainfall_mm} mm (C = ${h.runoff_coefficient})`;

    document.getElementById("res-target-storage").textContent = `${d.target_storage_m3.toLocaleString()} m³`;
    document.getElementById("res-depth").textContent = `${d.recommended_depth_m} m (Water: ${d.water_depth_m}m + Freeboard: ${d.freeboard_m}m)`;
    document.getElementById("res-top-dim").textContent = `${d.length_m} m (L) × ${d.width_m} m (W)`;
    document.getElementById("res-top-area").textContent = `${d.top_surface_area_m2.toLocaleString()} m²`;
    document.getElementById("res-base-area").textContent = `${d.bottom_base_area_m2.toLocaleString()} m²`;
    document.getElementById("res-excavation").textContent = `${d.excavation_volume_m3.toLocaleString()} m³`;

    document.getElementById("res-coords").textContent = `${loc.lat.toFixed(5)}, ${loc.lon.toFixed(5)}`;
    document.getElementById("res-elev").textContent = `${loc.elevation_m} m`;
    document.getElementById("res-slope").textContent = `${loc.slope_pct}%`;
    document.getElementById("res-relief").textContent = `${t.elevation_stats.relief_m} m (${t.elevation_stats.min_m}m - ${t.elevation_stats.max_m}m)`;
    document.getElementById("res-flat-area").textContent = `${t.slope_stats.flat_area_pct}%`;
}

function populateCatchmentSidebar(data) {
    const panel = document.getElementById("results-panel");
    panel.classList.remove("hidden");

    const c = data.catchment_area;
    const d = data.pond_design;
    const h = data.hydrology;
    const loc = data.pond_location;

    document.getElementById("report-mode").textContent = loc.selection_mode || "Manual Coordinate Site";
    document.getElementById("res-catchment-ha").textContent = `${c.hectares.toLocaleString()} ha`;
    document.getElementById("res-catchment-m2").textContent = `${Math.round(c.sq_meters).toLocaleString()} m² (${c.sq_km} km²)`;

    document.getElementById("res-runoff-m3").textContent = `${Math.round(data.annual_runoff_volume_m3).toLocaleString()} m³`;
    document.getElementById("res-rainfall-source").textContent = `R = ${h.annual_rainfall_mm} mm (C = ${h.runoff_coefficient})`;

    document.getElementById("res-target-storage").textContent = `${d.target_storage_m3.toLocaleString()} m³`;
    document.getElementById("res-depth").textContent = `${d.recommended_depth_m} m (Water: ${d.water_depth_m}m + Freeboard: ${d.freeboard_m}m)`;
    document.getElementById("res-top-dim").textContent = `${d.length_m} m × ${d.width_m} m`;
    document.getElementById("res-top-area").textContent = `${d.top_surface_area_m2.toLocaleString()} m²`;
    document.getElementById("res-base-area").textContent = `${d.bottom_base_area_m2.toLocaleString()} m²`;
    document.getElementById("res-excavation").textContent = `${d.excavation_volume_m3.toLocaleString()} m³`;

    document.getElementById("res-coords").textContent = `${loc.lat.toFixed(5)}, ${loc.lon.toFixed(5)}`;
    document.getElementById("res-elev").textContent = `${loc.elevation_m} m`;
    document.getElementById("res-slope").textContent = `${loc.slope_pct}%`;
}

function exportGeoJSON() {
    if (!currentResults || !currentResults.catchment_geojson) {
        alert("No catchment data available to export.");
        return;
    }
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(currentResults.catchment_geojson, null, 2));
    const downloadAnchor = document.createElement("a");
    downloadAnchor.setAttribute("href", dataStr);
    downloadAnchor.setAttribute("download", "catchment_watershed.geojson");
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
}
