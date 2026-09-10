#!/usr/bin/env python3
"""Find the teleports (big position jumps) in a capture and draw them on the Aeternum map.

    # what the jumps were
    .venv-capture/bin/python Tools/nw_capture/experimental/nw_map_jumps.py \
        --ledger Tools/nw_capture/captures/offline-position-scratch/ledger.bin

    # emit the JS that draws them, then run it against the map tab
    .venv-capture/bin/python .../nw_map_jumps.py --ledger ... --js /tmp/nwc/jumps.js
    CDP_PORT_FILE=/tmp/nwc/cdp_port_9223 cdp eval <target> "$(cat /tmp/nwc/jumps.js)"

A jump is a step longer than --jump units between consecutive distinct samples. Positions come
from worldPosAbs in the ledger (east, north, elevation), the same numbers the map uses.
"""
import argparse
import json
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "offline"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))

MAP_JS = """(function () {
  const DATA = %s;
  const el = document.querySelector('.leaflet-container');
  if (!el) return 'no-map-container';
  const key = Object.keys(el).find(function (k) { return k.startsWith('__reactFiber$'); });
  const seen = new Set(); let map = null;
  function walk(o, d) {
    if (!o || d > 6 || map) return;
    if (typeof o === 'object') {
      if (seen.has(o)) return; seen.add(o);
      try { if (typeof o.setView === 'function' && o._container && typeof o.panTo === 'function') { map = o; return; } } catch (e) {}
      if (Array.isArray(o)) { for (const v of o.slice(0, 12)) walk(v, d + 1); return; }
      for (const k of Object.keys(o).slice(0, 40)) { try { walk(o[k], d + 1); } catch (e) {} }
    }
  }
  walk(el[key], 0);
  if (!map) return 'no-map-instance';
  if (window.__nwTp) window.__nwTp.forEach(function (l) { try { map.removeLayer(l); } catch (e) {} });
  const layers = []; let bounds = null;
  function ext(x) { bounds = bounds ? bounds.extend(x) : x; }
  DATA.runs.forEach(function (run) {
    const latlngs = run.map(function (p) { return [p[1], p[0]]; });
    if (latlngs.length > 1) { const l = L.polyline(latlngs, {color:'#8d8d8d', weight:3, opacity:0.95}).addTo(map); layers.push(l); ext(l.getBounds()); }
    else { const m = L.circleMarker(latlngs[0], {radius:3, color:'#8d8d8d', fillOpacity:1}).addTo(map); layers.push(m); ext(L.latLngBounds([latlngs[0]])); }
  });
  DATA.jumps.forEach(function (j, i) {
    const a = [j[0][1], j[0][0]], b = [j[1][1], j[1][0]];
    const line = L.polyline([a, b], {color:'#ff2fb0', weight:4, dashArray:'12 9'}).addTo(map);
    layers.push(line); ext(line.getBounds());
    layers.push(L.circleMarker(a, {radius:9, color:'#111', weight:2, fillColor:'#12d67b', fillOpacity:1})
      .bindTooltip('T' + (i + 1) + ' PARTENZA ' + j[0][0].toFixed(0) + ', ' + j[0][1].toFixed(0) + ' (q ' + j[0][2].toFixed(0) + ')', {permanent:true, direction:'right'}).addTo(map));
    layers.push(L.circleMarker(b, {radius:9, color:'#111', weight:2, fillColor:'#ff3b1f', fillOpacity:1})
      .bindTooltip('T' + (i + 1) + ' ARRIVO ' + j[1][0].toFixed(0) + ', ' + j[1][1].toFixed(0) + ' (q ' + j[1][2].toFixed(0) + ')', {permanent:true, direction:'right'}).addTo(map));
  });
  window.__nwTp = layers;
  if (bounds) map.fitBounds(bounds, {padding: [90, 90]});
  const c = map.getCenter();
  return JSON.stringify({runs: DATA.runs.map(function (r) { return r.length; }), jumps: DATA.jumps.length, center: [c.lat, c.lng], zoom: map.getZoom()});
})()
"""


def positions(ledger):
    from decode_alc_state import iter_records
    from decode_in_bodies import channel_stream, iter_frames
    out = []
    for _off, _cnt, body, _tr in iter_frames(channel_stream(str(ledger))):
        for _s, _v1, _v2, _flag, _poff, fields in iter_records(body):
            for _bit, name, chunk, _value in fields:
                if name == "worldPosAbs" and len(chunk) == 10:
                    east, north = struct.unpack(">ff", chunk[:8])
                    raw = struct.unpack(">H", chunk[8:])[0]
                    sample = [round(east, 2), round(north, 2), round(raw / 65535 * 1100 - 100, 2)]
                    if not out or sample != out[-1]:
                        out.append(sample)
    return out


def split(samples, jump):
    runs, jumps, current = [], [], [samples[0]] if samples else []
    for a, b in zip(samples, samples[1:]):
        if ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5 > jump:
            jumps.append([a, b])
            runs.append(current)
            current = [b]
        else:
            current.append(b)
    if current:
        runs.append(current)
    return runs, jumps


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--jump", type=float, default=100.0, help="units above which a step is a jump")
    parser.add_argument("--js", type=Path, help="write the map-drawing JS here")
    args = parser.parse_args(argv)

    samples = positions(args.ledger)
    runs, jumps = split(samples, args.jump)
    print(f"{len(samples)} posizioni distinte, {len(runs)} segmenti, {len(jumps)} salti")
    for index, (a, b) in enumerate(jumps, 1):
        distance = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
        print(f"  T{index}: ({a[0]:.1f}, {a[1]:.1f}, q{a[2]:.1f}) -> "
              f"({b[0]:.1f}, {b[1]:.1f}, q{b[2]:.1f})   {distance:.1f} unita'")
    if args.js:
        args.js.write_text(MAP_JS % json.dumps({"runs": runs, "jumps": jumps}))
        print(f"js scritto in {args.js}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
