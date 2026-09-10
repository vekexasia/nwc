# Live position map feasibility

## Decision

A live player marker and trail are **not a verified end-to-end feature today**. Passive live DTLS capture is working, but the current application stops at Carrier framing and opaque payload bytes. First Light supplies historical protocol clues, not a complete, validated position decoder. NWDB supplies neither live positions nor a verified general data API. A map cannot be promised from packet capture alone.

## Demonstrated capability

The existing capture path records plaintext `SSL_read`/`SSL_write` bytes with direction, hook timestamp, session pointer, and payload length in a private ledger (`Tools/nw_capture/_dtls_ledger.js:14-27`). It flushes Frida batches every 25 ms or at 32 KiB (`:42-45,198-206`). The runner writes batches during capture and performs final flush/metadata work only during cleanup (`Tools/nw_capture/_runner.py:242-283,322-335`).

The existing decoder validates the Carrier datagram header, LZ4 body, message framing, channels, sequence fields, and payload boundaries (`Tools/nw_capture/decode_dtls_ledger.py:176-232`). It is an offline whole-file iterator, not an incremental live parser (`:235-247`). Existing decoded local ledgers contain transport fields and `payload_hex`; they do not contain application type IDs, replica/entity IDs, coordinates, self identity, or trail points. Aggregate read-only inspection of the three existing decoded ledgers found 51,671 records, 100,052 Carrier messages, zero Carrier decoder errors, and 46,038 records with unconsumed trailer bytes.

The completed `Test teleport` runtime evidence reports 6,354 valid records, 11,923 Carrier messages, 4,884 incoming and 1,470 outgoing records, with final flush acknowledged and no decoder errors. This demonstrates reliable plaintext Carrier capture, not position decoding. The web worker publishes only `{bytes, count, errors, ready}` (`Tools/nw_capture/web/worker.py:24-42`); the server accepts those counters and exposes the session snapshot (`Tools/nw_capture/web/server.ts:64-79,190-198`), while the browser renders status/lifecycle fields only (`Tools/nw_capture/web/app.js:6-29`).

## First Light: role and current answer

**Answer: no verified live positioning decoder is available from First Light now.** It is a historical, explicitly defunct reverse-engineering/private-server repository, not an active supported protocol source (`docs/Network/first-light-research.md:34-46`). Its value is source and analysis evidence:

- The historical Carrier codec describes the 4-byte envelope and inner message records, but not gameplay semantics (`first-light/server/javelin/frame.py`, especially lines 1-35 and 120-220 in the downloaded snapshot).
- Its type-`0x08` codec validates an 11-byte anchor or a UUID prefix and deliberately leaves the remainder as `opaque` (`first-light/server/javelin/chunked_stream_08.py:1-15,45-65,108-165`). The historical analysis says the per-subtype handler, runtime trace, or deeper static RE is still needed (`first-light/analysis/wire_type_0x08.md:79-120`). This is the principal likely location for replicated world state.
- The class catalog identifies `MB::PositionInTheWorldReplicatedState` as `type_idx = 13`, gives a candidate UUID, and names Marshal/Unmarshal addresses (`Catalog/README.md:10-49`; `Catalog/uuid_to_class.json:98593-98621`). That establishes a strong semantic anchor, not a packet decoder or proof that the local player uses it.
- The repository's `docs/Network/packet_system.md:242-361` presents a proposed StateBundle/member layout and compressed XYZ fields. It is useful as a decoding hypothesis. Its sample coordinates are not demonstrated by the current capture output and must not be treated as a validated player position.
- Movement names such as `ActorMover::MoveActorMsg` and `CommitMovementMsg` are present in the historical type inventory (`first-light/analysis/message_inventory.md:1555-1589`), but the replay analysis says these are generally embedded in anonymous `0x08` state-bundle traffic rather than exposed as named top-level messages (`first-light/analysis/typeregistry_vs_replay.md:40-72,94-117`).

One contradiction is resolved by the downloaded source: the earlier wording that `0x1096` has “no codec” is too broad. First Light does have a **structural** `0x1096` codec and dispatch entry (`first-light/server/javelin/frame_config_1096.py:1-15,80-127`; `dispatch.py:74-116`). That module itself says its field names are shape-based, derived from one capture, and not authoritative semantics (`frame_config_1096.py:1-15,20-45`). Its float-looking fields therefore cannot be used as a validated player coordinate. The `0x1096`/`0x1097` pair is spawn-related context at most (`first-light/analysis/replay_message_inventory.md:851-894`).

### Missing protocol knowledge

Before emitting a position, the project must still prove all of the following:

1. Incremental Carrier stream handling across ledger batches, including reliable ordering, chunk reassembly, channel streams, and message boundaries.
2. The actual `0x08` StateBundle inner-record format and subtype dispatch, including the complete body schema for member type 13.
3. The coordinate codec: X/Y decompression constants, Z encoding, units, precision, axis order, and whether updates are absolute or relative.
4. Replica/entity correlation and self selection. A position component applies to replicated entities; `PlayerManager` self-identification/ownership must be tied to the same replica, not guessed from timing or the first entity seen.
5. Evidence that the candidate values change with a teleport and with ordinary movement while unrelated entities do not, across at least two movement segments.

## NWDB: role and current answer

**Answer: NWDB does not provide a verified live-position feed.** It is the independent New World Database website, not an Amazon Games service (`docs/Network/nwdb-research.md:3-11`). No public general API, source repository, or data dump was verified. The only documented developer integration found is Tooltip Syndication via `https://nwdb.info/embed.js`, which is not a position API (`docs/Network/nwdb-research.md:13-18`). NWDB's terms prohibit scraping, unusual/script access, and reproducing content elsewhere (`https://nwdb.info/terms-and-conditions`).

Runtime inspection of the public map found a MapLibre raster renderer, versioned tile configuration, and an internal `window.postMessage` `SET_EXTERNAL_DATA` path accepting GeoJSON overlays. This shows that client-supplied markers can plausibly be visualized, but it is an undocumented implementation detail, not a supported integration contract. The inspected map transform is a visualization transform only; it does not prove that game XYZ shares NWDB's origin, scale, axis signs/order, zone, or projection. Tile/data reuse and rehosting therefore require a separate permission and licensing decision. Use NWDB only if its operator permits the exact integration; otherwise use an independently owned or licensed basemap.

### Missing map knowledge

Even with decoded game XYZ, the following remain unproven: world-to-map origin and scale, X/Y axis and sign convention, zone/level selection, landmark alignment, vertical treatment, and permission to load or rehost map tiles/data. The smallest safe first visualization is a neutral coordinate plot, not an NWDB-dependent map.

## Smallest staged proof using existing Test teleport data

No new capture or implementation is authorized for this investigation. The smallest credible next proof is offline and staged:

1. Feed the existing Test teleport ledger through a stateful copy of the already demonstrated Carrier decoder, without exposing raw payloads. Confirm channel-1 stream ordering, chunk reassembly, top-level type extraction, and the `0x08` path.
2. Apply the candidate StateBundle/member-13 schema only as a hypothesis. Produce private diagnostics for candidate timestamps, replica IDs, presence bits, and XYZ values; do not call them positions yet.
3. Correlate the candidate stream with the known teleport interval. Acceptance requires a reproducible discontinuity or movement delta on one stable replica and complete consumption of each decoded member. The existing Test teleport evidence alone cannot establish absolute map coordinates or own-player identity if it lacks a second known landmark/movement segment.
4. Only after that offline result is coherent should the operator authorize an extended in-world capture with deliberate movement in multiple directions and known landmarks. That capture is needed to validate self selection, units/axes, and the game-to-map transform.

## Expected live flow and bounded trail

Once protocol validation exists, the expected flow is:

`SSL hooks -> private ledger batch -> incremental Carrier/reassembly state -> 0x08/member decoder -> validated self replica -> {timestamp, x, y, z} -> bounded server snapshot -> browser marker/trail`.

The current worker/server cadence (about 0.5 s) and browser polling (0.75 s) can support a coarse moving marker, but not a faithful 30 Hz trail. A trail should be a fixed-size, fixed-age ring containing only validated points, with duplicate/near-zero movement samples coalesced, large time gaps marked or split, and a new session clearing prior points. Raw payloads and other entities should never be sent to the browser. A faster bounded push/endpoint would be needed for a smooth trail.

## Recommendation

Do not build the NWDB integration or promise a live map yet. First prove the `0x08` StateBundle -> member-13 decoder and self-replica correlation against the existing Test teleport data. Then validate the coordinate transform with an authorized multi-segment capture, using a neutral or permissioned basemap. First Light is a historical protocol reference; NWDB is, at most, a separately permissioned visualization source.

### Primary sources

- First Light repository: https://github.com/nw-private-server/first-light
- First Light Carrier codec: https://github.com/nw-private-server/first-light/blob/main/server/javelin/frame.py
- First Light type-0x08 analysis: https://github.com/nw-private-server/first-light/blob/main/analysis/wire_type_0x08.md
- First Light post-V3/in-world notes: https://github.com/nw-private-server/first-light/blob/main/docs/post-v3-sequence.md
- First Light codec queue: https://github.com/nw-private-server/first-light/blob/main/analysis/queued_work.md
- NWDB: https://nwdb.info/
- NWDB terms: https://nwdb.info/terms-and-conditions
- NWDB Tooltip Syndication: https://nwdb.info/tooltips
- NWDB documented embed script: https://nwdb.info/embed.js
