// nw_map_trail.js - draw a decoded position trail on the Aeternum Map (aeternum-map.th.gl).
//
// Usage: open https://aeternum-map.th.gl/ in Chrome with remote debugging, then evaluate this file
// with a points array in game coordinates, e.g.
//
//   cdp eval <target> "(function(){ const NW_POINTS = [[8877.2,3126.6],[8879.1,3124.5]]; $(sed -n '10,$p' nw_map_trail.js) })()"
//
// or simply paste it in the console after replacing NW_POINTS. Points are [x, y] exactly as
// decode_position.py prints them (first wire float, second wire float); the map's own coordinate
// readout (bottom right) uses the same units, so no conversion is needed.
//
// It finds the Leaflet instance through the React fiber of the map container, clears any previous
// trail drawn by this file, draws the polyline with a marker per sample (green start, red end,
// yellow every tenth sample) and fits the view to the trail.
(function (points) {
    const PTS = points.map(function (p) { return [p[1], p[0]]; });   // Leaflet wants [lat, lng]
    const el = document.querySelector(".leaflet-container");
    if (!el) return "no-map-container";
    const key = Object.keys(el).find(function (k) { return k.startsWith("__reactFiber$"); });
    const seen = new Set();
    let map = null;
    function walk(o, d) {
        if (!o || d > 6 || map) return;
        if (typeof o === "object") {
            if (seen.has(o)) return;
            seen.add(o);
            try {
                if (typeof o.setView === "function" && o._container && typeof o.panTo === "function") {
                    map = o;
                    return;
                }
            } catch (e) { /* not the map */ }
            if (Array.isArray(o)) {
                for (const v of o.slice(0, 12)) walk(v, d + 1);
                return;
            }
            for (const k of Object.keys(o).slice(0, 40)) {
                try { walk(o[k], d + 1); } catch (e) { /* ignore */ }
            }
        }
    }
    if (key) walk(el[key], 0);
    if (!map) return "no-map";

    for (const layer of (window.__nwTrail || [])) {
        try { map.removeLayer(layer); } catch (e) { /* ignore */ }
    }
    if (window.__nwPin) { try { map.removeLayer(window.__nwPin); } catch (e) { /* ignore */ } }

    const layers = [];
    const line = L.polyline(PTS, { color: "#ff2fb0", weight: 3, opacity: 1, lineJoin: "round" }).addTo(map);
    layers.push(line);
    PTS.forEach(function (p, i) {
        const isFirst = i === 0, isLast = i === PTS.length - 1;
        const colour = isFirst ? "#12d67b" : isLast ? "#ff3b1f" : "#ffffff";
        const radius = (isFirst || isLast) ? 7 : 3;
        layers.push(L.circleMarker(p, { radius: radius, color: "#111", weight: 1, fillColor: colour, fillOpacity: 1 })
            .bindTooltip((isFirst ? "START " : isLast ? "END " : "sample " + i + " ") +
                         p[1].toFixed(1) + ", " + p[0].toFixed(1))
            .addTo(map));
        if (i % 10 === 0 && i > 0) {
            layers.push(L.circleMarker(p, { radius: 5, color: "#111", weight: 1, fillColor: "#ffd400", fillOpacity: 1 })
                .bindTooltip("sample " + i).addTo(map));
        }
    });
    window.__nwTrail = layers;
    map.fitBounds(line.getBounds(), { padding: [80, 80] });
    const centre = map.getCenter();
    return JSON.stringify({
        zoom: map.getZoom(), center: [centre.lat, centre.lng], points: PTS.length,
        start: PTS[0], end: PTS[PTS.length - 1],
    });
})(NW_POINTS);
