# Placing decoded New World player positions on the community maps

Scope: answers the four questions from measured data only. Raw sources are listed at the
bottom; every claim below carries the exact URL / file+symbol it came from. Anything I could
not confirm is marked **unverified**.

Input data used: `/tmp/nw_positions.csv` (765 abs rows, `ts,x,y,z`) and `/tmp/nw_positions.json`
(765 `abs` samples, 466 unique by `ts`+`raw`). Track used: `/tmp/nwdb-map/trail.json`.

---

## 1. Coordinate convention of our three components

**Verdict (verified): map `X` = our first float, map `Y` = our second float, map `Z` = the
quantised u16 (elevation). Units are the game's own world units, passed to the community maps
1:1 with no scaling. The maps' origin (0, 0) is the same as the game world origin.**

Evidence that the community maps use `(X=east, Y=north, Z=height)` and put the player at
leaflet `[Y, X]`:

1. `Kattoor/aeternum-map`, `src/app/contexts/PositionContext.tsx`:
   ```ts
   const position: [number, number] = [location.y, location.x];
   ```
   i.e. the in-game `location.x` becomes the map's horizontal (leaflet lng) and `location.y`
   the vertical (leaflet lat). Source:
   https://github.com/Kattoor/aeternum-map/blob/main/src/app/contexts/PositionContext.tsx
2. Live deployment bundle `https://aeternum-map.th.gl/assets/MarkersContext-DKpc4JRJ.js`
   (fetched 2026-09-10, in `/tmp/nwdb-map/raw/amchunks/MarkersContext-DKpc4JRJ.js`):
   ```js
   const El = K.extend({}, K.CRS.Simple, {transformation: new K.Transformation(1/16, 0, -1/16, 0)});
   ...
   ro = t => { const e = t.get("x"), r = t.get("y"), n = t.get("zoom");
               return !e || !r || !n ? null : {x: +e, y: +r, zoom: +n}; }
   ...
   i.x ? y.setView([i.y, i.x], e || i.zoom, {animate:!1, noMoveStart:!0}) : y.fitBounds(w, ...)
   ```
   `setView([y, x])` = leaflet `[lat=y, lng=x]` with a `1/16`-scaled simple CRS.
3. Live deployment bundle `https://aeternum-map.th.gl/assets/AddResources-Cfp9sHrB.js`: the
   position editor renders `[<X>, <Y>,]` with `placeholder:"e.g. 9015.32", min:0, max:14336` and
   `placeholder:"e.g. 5015.12", min:0, max:14336`, and the "use current location" button does
   `n([o.location[1], o.location[0], t[2]])` into `[X, Y, Z]`.
4. `Kattoor/aeternum-map`, `src/app/components/WorldMap/useWorldMap.ts` defines the default
   whole-map view as `latLng(0, 4000)` to `latLng(10000, 14336)` (i.e. Y 0..10000, X 4000..14336)
   with the same `Transformation(1/16, 0, -1/16, 0)`. Source:
   https://github.com/Kattoor/aeternum-map/blob/main/src/app/components/WorldMap/useWorldMap.ts

Empirical confirmation that our *first* float is `X` and the *second* is `Y` (and not the other
way round). Using `https://aeternum-map.th.gl/api/markers` (55739 markers; 3620 with a
non-zero elevation) and the 48 unique positions of the local track:

| assignment | median distance to nearest marker | median abs(err) vs marker elevation |
|---|---|---|
| X = first float, Y = second float | **34.3** | **2.25** |
| X = second float, Y = first float | 2642.4 | 66.35 |

(script: `python3` inline, marker field `position = [x, y, z]`; e.g. the track end
`(8876.59, 3096.67, z 73.96)` has the marker `[8878.75, 3099.29, 73.62]` 3.5 units away with
elevation 73.62.) The correct orientation agrees with the nearest static marker's elevation to
~2 m; the swapped one is off by ~66 m and lands ~2.6 km from any recorded object.

Also verified: the elevation is the *third* field, not the second. Our decoded elevation column
runs 55.97..74.36, the same range as `z` in the marker data (median 0), while our second float
(3003..3129) is in the horizontal range of marker `y` values.

Naming clash to be aware of: `docs/Network/alc-protocol-reference.md:238-243` labels the wire layout
`float32 BE x`, `float32 BE z`, `u16 BE` quantised third component. That is the repo's field naming for
the *decode*, not the map's axes: the second float is a **horizontal** coordinate (aeternum-map's `Y`),
and the quantised u16 is the height (aeternum-map's `Z`). Do not read the repo's `z` label as the map's `y`
axis. The map orientation is settled by the axis-assignment test above, not by the repo's label.

Reference example `(9304, 2912, 85)`: with the convention above, that is X 9304 / Y 2912 /
elevation 85. Nearest aeternum-map features: `Corinth` settlement `[9339, 2710]`, `Amrine
Excavation` `[9306, 3214]`, `Excavated Shrine` `[9341, 3171]` - i.e. Windsward, just south of
Amrine. **Inferred** (the example's own origin was not stated in any source I read; only the
interpretation of the numbers is verified).

Units: I did not find a primary source that states "1 unit = 1 metre". What *is* verified is that
the maps consume the game numbers unscaled (evidence 1-4) and that marker/decoded values agree
numerically. "Metres" is therefore a **community usage convention, unverified** in the sources I
read.

Origin: same as the game world origin. The community marker set spans X 205..14255 and
Y 48..11259 (`https://aeternum-map.th.gl/api/markers`), consistent with an origin at (0, 0)
in the world's south-west corner, not at the map image corner. Exact map image bounds are
whatever the deployment uses; the repo's default view is X 4000..14336, Y 0..10000.

## 2. Which region the track is in

**Verdict: Windsward** (X 8786..8877, Y 3058..3097). Nearest named places from
`https://aeternum-map.th.gl/api/markers` (fields `name`, `position = [x, y, z]`, distances from
the track centre 8800/3060):

| marker | position | distance |
|---|---|---|
| `Bastion Windsward` (fort) | [8928.24, 3289.14] | 262 |
| `North Windsward Watch` (fort) | [8536, 3148] | 278 |
| `Central Windsward Watch` (fort) | [8464, 2850] | 396 |
| `South Windsward Watch` (fort) | [8880, 2369] | 696 |
| `Amrine Excavation` (expedition) | [9306, 3214] | 529 |
| `Scenic Painting of the Elin River` (vista) | [8648.25, 2804.25] | 297 |
| `Corinth` (settlement) | [9339, 2710] | 643 |

The track runs along the Elin River valley area of northern Windsward, between the
North/Central Windsward Watch line and Bastion Windsward. It is **not** inside a settlement:
the nearest settlement is Corinth, 643 units away.

## 3. Interactive maps: deep links

### 3.1 `aeternum-map.th.gl` - YES (this is the one I use)

The live app parses `x`, `y`, `zoom` from the query string; **all three are required**
(`!e || !r || !n ? null`). Evidence: `https://aeternum-map.th.gl/assets/MarkersContext-DKpc4JRJ.js`
(fetched 2026-09-10; local copy `/tmp/nwdb-map/raw/amchunks/MarkersContext-DKpc4JRJ.js`), symbols
`ro` (parser) and the `setView([i.y, i.x], ...)` call site. The same app writes that URL back on
every move (`d.set("x", ...); d.set("y", ...); d.set("zoom", ...)`), and the upstream source has
the same logic in `useWorldMap.ts`
(https://github.com/Kattoor/aeternum-map/blob/main/src/app/components/WorldMap/useWorldMap.ts).

Template (game coords, all three mandatory):

```
https://aeternum-map.th.gl/?x=<gameX>&y=<gameY>&zoom=<zoom>
```

Filled in for our track centre:

```
https://aeternum-map.th.gl/?x=8800&y=3060&zoom=6
```

There is also a viewport deep link, `?bounds=west,south,east,north` (parsed by the same bundle:
`bounds=(-?\d+\.?\d+),(-?\d+\.?\d+),(-?\d+\.?\d+),(-?\d+\.?\d+)` -> `[[+m[2], +m[1]], [+m[4], +m[3]]]`
= `[[latMin,lngMin],[latMax,lngMax]]`), and `?embed=true`.

Caveat: the `zoom` range of the current deployment is **unverified** (I found no `maxZoom` in the
live chunks). If 6 is out of range the app clamps it; the centre is unaffected.

### 3.2 `metaforge.app/new-world/map/` - YES, but coordinate value partly unverified

`https://metaforge.app/new-world/map/js/app.0c1c1bf8.js` (fetched 2026-09-10; local copy
`/tmp/nwdb-map/raw/mf_app.js`) contains a vue-router in hash mode
(`mode:"hash", base:"/new-world/map/"`, route `/:zone?`) and a `"$route.query"` watcher:

```js
"$route.query":{ immediate:!0, handler:function(e){
  if(null!=e && null!=e.lng && null!=e.lat){ var t=Number(e.lng), a=Number(e.lat);
    "number"===typeof t && "number"===typeof a && this.setUrlMarkerLatLng([a,t]); }
  else ... e.npc ...
  if(null!=e && null!=e.zoom){ var n=Number(e.zoom); "number"===typeof n && this.setZoomLevel(n); } } }
```
and `setUrlMarkerLatLng:function(e,t){ ... n=[Object(ae["p"])(t[0]), t[1]] ... }`.

So the template is

```
https://metaforge.app/new-world/map/#/?lng=<gameX>&lat=<gameY>&zoom=<zoom>
```

but note `lat` is passed through a minified transform `ae["p"]` that I could not resolve from the
bundle (no source map: `app.0c1c1bf8.js.map` returns 403). It applies only to the latitude, so it
is probably a Y-flip, but **unverified**. There is also `?npc=<name>` and `?m=<lng>,<lat>` (that
one is used untransformed, evidence: `e.split(",")` -> `[Number(t[1]), Number(t[0])]`), plus
`&embed`.

Map data note: metaforge's coordinates are also game coordinates - the same bundle takes the
aeternum-map websocket position as `[o.location[1], o.location[0], o.rotation]` (= `[Y, X]`) and
stores it, and its own position form sets `x = playerLocation[0]`, `y = playerLocation[1]`.

### 3.3 `nwdb.info/map` - NO coordinate deep link found

The `/map` route is SvelteKit node 20 -> `https://nwdb.info/_app/immutable/nodes/20.CwzSQ0C5.js`
(route table `"/(map)/map":[20]` in `https://nwdb.info/_app/immutable/entry/app.DBzg3tH5.js`;
local copy `/tmp/nwdb-map/raw/nwdb_node20.js`). The only query-string reads in that 964 KB bundle
are the MapLibre raster tile template (`x={x}&y={y}&z={z}`) and its companion parser:

```js
function hm(Be){const $e=new URLSearchParams(Be),Ke=JSON.parse($e.get("config")),nt=$e.get("layer"),
  Rt=Number($e.get("x")),ir=Number($e.get("y")),C=Number($e.get("z")); ...}
function bm(Be){const $e=new URLSearchParams(document.location.search), ...}
```
i.e. `x`/`y`/`z` there are **tile** indices, not world coordinates. My grep for
`get("lat"|"lng"|"zoom"|"center"|"position"|"coord")` returned nothing. No player/coordinate deep
link. Smallest reliable alternative: the page's own MapLibre renderer accepts client-supplied
GeoJSON through `window.postMessage({type:"SET_EXTERNAL_DATA", ...})` (found in the same bundle and
noted in `docs/Network/live-position-map-feasibility.md`), i.e. an overlay injection rather than a
URL. That path is undocumented and tied to whatever NWDB serves today, and NWDB's terms forbid
scraping/rehosting (https://nwdb.info/terms-and-conditions) - so I did not build on it.

### 3.4 `newworldminimap.com/map` - NO coordinate deep link

`https://newworldminimap.com/static/js/main.bdd4caf1.chunk.js` (fetched 2026-09-10; local copy
`/tmp/nwdb-map/raw/nwmm_main.js`) reads exactly three query parameters:

```js
const e=window.location.search, a=new URLSearchParams(e).get("code");   // join a group
... new URLSearchParams(window.location.search); e.get("code"); this.websocket_uri_override=e.get("ws_override");
... .get("name")
```
(`code`, `name`, `ws_override`). No `x`/`y`/`lat`/`lng`/`zoom`/`position`. The `/map` page is a
group-sharing view fed over a local websocket, so the smallest reliable alternative is the page's
own flow (join/share a group code) or a coordinate read-out, not a URL. **Unverified** whether a
newer build adds one; I only read this bundle.

## 4. Deliverables

### `/tmp/nwdb-map/map-link.txt`
```
https://aeternum-map.th.gl/?x=8800&y=3060&zoom=6
```
(one line; aeternum-map, centred on the track centre; `zoom` may be edited.)

### `/tmp/nwdb-map/trail.json`
204 `{ts, x, y, z}` objects, `ts` = epoch ms, `x` = game X (east), `y` = game Y (north),
`z` = decoded elevation. This is the local player's track only: the unique abs samples were
associated by nearest-neighbour with a 1.5 s / 25-unit gate; the largest resulting track is the
monotonic walk that runs `x 8786.66 -> 8876.59`, `y 3058.37 -> 3096.67`, `z 63.89 -> 73.96`
over ts 1789052581172..1789052600331 (t+45.4 s .. t+64.5 s of the capture). 48 of those 204 samples
are distinct positions; the rest are repeated replicas of the same position. The other entities in
the file (stationary ~8876/3120-3127, a walker at ~8866..8850/3096, entities near 8779-8799/3006-3018)
are excluded.

Note: the ranges quoted in the task brief (x 8786.66..8893.83, second float 3003.97..3126.63,
elev 58.03..74.35) are the bounding box of *all* entities in the file, not of one track.

### `/tmp/nwdb-map/trail.html`
Self-contained page (no network, no CDN) that draws the 48 distinct track positions as a polyline
on a plain canvas with axes labelled in game coordinates, plus a crosshair at (8800, 3060) and
start/end markers. It is the canvas fallback, and the page says so, because the tile scheme
documented in the aeternum-map repo is no longer served: I fetched
`https://aeternum-map.th.gl/assets/map/map_l2_y010_x034.webp` (and neighbours) and every one
returned `200 text/html` of 26139 bytes, i.e. the SPA shell, not an image. The same applies to
`https://aeternum-map.th.gl/maps/aeternum.webp?v=4` (also `text/html`, 26139 bytes). So there is
no verified, directly usable raster tile/coordinate scheme to overlay the track on.

## Verified vs inferred

Verified (read from the stated source and quoted above):
- Community map convention: `X` = east, `Y` = north, `Z` = elevation; player is plotted at
  leaflet `[Y, X]` with an unscaled simple CRS (repo + live bundle).
- Our first float is `X`, our second float is `Y`, the quantised u16 is `Z`; marker agreement
  test above (34 m / 2.25 m vs 2.6 km / 66 m).
- The track lies in Windsward (nearest forts/settlement table).
- `aeternum-map.th.gl` accepts `?x=&y=&zoom=` (all three required) and also `?bounds=`.
- `metaforge.app/new-world/map/` accepts `?lng=&lat=&zoom=` (hash mode) plus `?npc=` and `?m=`.
- `nwdb.info/map` and `newworldminimap.com/map` have no coordinate deep link in the bundles read.
- The aeternum-map repo tile URLs are not served by the live site (they return the HTML shell).

Inferred / unverified:
- "1 unit = 1 metre" in community usage (no primary source read states it).
- That `(9304, 2912, 85)` is a spawn point (the numbers map to Windsward near Amrine; the origin of
  the example was not stated).
- The `lat` transform `ae.p` in metaforge: the URL accepts `lat`, but whether the raw game `Y`
  is the correct value for it is unverified.
- The usable `zoom` range of the live aeternum-map deployment.
- Whether newer builds of nwdb/NWMM add parameters not present in the bundles read today.
- Nothing here was verified by rendering a browser; all map claims come from reading the served
  JavaScript. The marker-agreement test in section 1 is the only end-to-end numeric check.

## Sources read (all fetched 2026-09-10)
- https://aeternum-map.th.gl/ , https://aeternum-map.th.gl/assets/index-DkKswZG4.js ,
  https://aeternum-map.th.gl/assets/MarkersContext-DKpc4JRJ.js ,
  https://aeternum-map.th.gl/assets/AddResources-Cfp9sHrB.js ,
  https://aeternum-map.th.gl/api/markers
- https://github.com/Kattoor/aeternum-map (`src/app/contexts/PositionContext.tsx`,
  `src/app/components/WorldMap/useWorldMap.ts`, `src/app/components/WorldMap/usePlayerPosition.ts`,
  `src/app/components/MapFilter/areas.ts`)
- https://metaforge.app/new-world/map/ , https://metaforge.app/new-world/map/js/app.0c1c1bf8.js
- https://nwdb.info/map , https://nwdb.info/_app/immutable/entry/app.DBzg3tH5.js ,
  https://nwdb.info/_app/immutable/nodes/20.CwzSQ0C5.js , https://nwdb.info/terms-and-conditions
- https://newworldminimap.com/map ,
  https://newworldminimap.com/static/js/main.bdd4caf1.chunk.js
- Repo context: docs/Network/nwdb-research.md, docs/Network/live-position-map-feasibility.md,
  docs/Network/alc-protocol-reference.md:238-249 (wire layout `float32 BE x`, `float32 BE z`,
  `u16 BE` quantised third component).
