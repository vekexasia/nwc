# Decoder state snapshot

Written for resuming after a conversation compaction. Everything below is on disk; nothing depends
on chat history. Read this first, then
[alc-protocol-reference.md](alc-protocol-reference.md) for the protocol detail.

## Answer to "can we do everything now?"

Yes for the position and the observed group-0 schema, no for unobserved group-1 entries and
field semantics that the trace does not identify.

- **Working**: the group-aware record and payload envelope, the verified mask reader, and the
  runtime group-0 reader map in `decode_alc_state.py`. The position payload still consumes exactly
  (east 8877.205 / north 3126.587 / elevation 72.079).
- **Observed but partial**: group 1 is only mapped for bit 0 in the supplied trace. Bits not set by
  the outer masks, and the semantic names of reordered group entries, remain unverified.
- **Still open**: the live map loop (feed the decoded positions into `nw_map_trail.js`) is not wired
  up yet.

The follow-up evidence is now incorporated in the reference doc (section 2.4 and open question 6):
20,013/20,013 mask raw-byte/value pairs verify the 1..9-byte mask branches, and the `alcact` trace
maps the per-index readers and their observed consumed widths.

## Where we are

**The player position is decoded and verified.** Out of the game's inbound network traffic we get
`(x, y, z)` in world coordinates. Evidence:

- Static: the ALC type factory (`FUN_142a3b050`) names the type `ALCReplicatedState` and builds its
  48-property schema (`FUN_142a35db0`); two properties are the position, with readers
  `0x142a433d0` (`worldPosAbs`, 10 wire bytes) and `0x142a43330` (`worldPosRel`, 3 wire bytes).
- Live: tracing those two readers while the operator walked (two 4 s walks, 12 s stops) produced a
  track where `x` advances monotonically by ~2 units per update:
  `x 8786.66 -> 8893.83`, second float `3003.97 -> 3126.63`, elevation `58.03 -> 74.35`.
- Independent: the axis assignment is verified against the community marker set (55739 markers).
  With the first float read as east and the second as north, the decoded positions sit a median of
  16.6 units from the nearest recorded marker with a median elevation error of 1.38; swapped it is
  781 units. The map shows the track on land in Windsward, along the Elin River valley, and the
  map's own readout uses the same units (e.g. `[8828.02, 3089.26]`). See 3.4 of the reference.

Where the numbers come from: `worldPosAbs` = two big-endian float32 then a quantised u16 in
`[-100, 1000]` (elevation); `worldPosRel` = three quantised deltas, `0xff` = "no update".

## Health: static field map recovered, live payload still open

Health is **not** an `ALCReplicatedState` property (all 63 checked). The actual network type is
`MB::VitalsComponentReplicatedState`, a custom group-aware handler rather than the ALC schema
builder. Its static field table and descriptor readers are now recovered; see
[health-field.md](health-field.md) for the complete 19-field table.

- UUID `0E721C70-2CDB-4E85-BAE4-D545FDC6D25B`, registry index 3241, **typeIndex 15**
  (`0x0f` as a one-byte type reference). The registry entry has an empty stored name; the
  binary registration-hook string supplies the C++ type name.
- `FUN_14671E040` registers the fields through `FUN_141775C60`. The custom unmarshal path
  calls `FUN_1417B4110` -> `FUN_1417B43C0`, which invokes selected member codec vtable
  `+0x30` readers.
- The health candidates are `HealthAmount` `+0x7c0` (reader `0x142a42f30`, 4 B),
  `HealthMax` `+0x838` (same reader, 4 B), lower-case `maxHealth` `+0x1000`
  (reader `0x142a42e10`, 2 B), and `HealthTickRate` `+0x8b0` (reader
  `0x142a42f80`, 2 B half). There is no registered `HealthRegen` row.
- `VitalsState` remains a false name hit: it is part of `MatchingVitalsState` and
  `NotMatchingVitalsState`, not a descriptor.
- Whether Vitals records are in the captures we hold is **not established**. Searching the streams
  for the type-15 pattern (`01 01 <V2> 0f`) gives 39 hits in the fight capture, 6 in the dodge
  capture and 0 in the walking capture, which is suggestive (only where health moved), but the bytes
  after those hits do not continue as a valid record chain, so they are probably false positives. The
  report that says the ledger holds only type `0x0b` records used a template that accepts a one-byte
  type field, which would miss any type whose index needs a longer varint.
  Settling it needs the record layer traced on a live capture: hook the type reference reader
  (`0x61ad00f`) and the payload-length copy (`0x2a4371a`) to get the length of every record type, then
  walk the stream exactly.
  Property order, mask bits and semantic values of the Vitals payload remain open for the same reason.
  The negative pass is kept as historical evidence in [health-field-deepseek.md](health-field-deepseek.md).
## Artifacts and where they live

In the repository (all new files, nothing committed yet):

| path | what |
|---|---|
| `docs/Network/alc-protocol-reference.md` | the reference: layers, readers, ALC fields, position encoding, playbook, dead ends |
| `docs/Network/alc-static-analysis.md` | raw Ghidra report (descriptors, readers, member offsets, unknowns) |
| `docs/Network/alc-runtime-fieldmap.md` | raw live-tracing report (record template, field map, negatives) |
| `docs/Network/offline-framing-findings.md` | chronological research log (S1..S3c plus the position result) |
| `docs/Network/nwdb-map-research.md` | community map research: coordinate convention, region, deep links |
| `docs/Network/position-decoder-plan.md` | the original step plan and its status |
| `Tools/nw_capture/experimental/decode_position.py` | pos_samples log -> positions (JSON, CSV) + track summary |
| `Tools/nw_capture/experimental/nw_pos_probe.js` | traces exactly the two position readers |
| `Tools/nw_capture/experimental/nw_field_probe.js` | traces the candidate field readers with values |
| `Tools/nw_capture/experimental/nw_capture_probe.py` | attach + capture with any probe |
| `Tools/nw_capture/experimental/nw_vkeys.py` / `.sh` | hold keys in the focused game, focus guard and restore |
| `Tools/nw_capture/experimental/nw_walktest.py` / `.sh` | capture plus driven keys in one run |
| `Tools/nw_capture/experimental/nw_vpad.py` / `.sh` | virtual gamepad (does not work unattended, see gotchas) |
| `Tools/nw_capture/experimental/nw_map_trail.js` | draws a decoded trail on the Aeternum map (Leaflet) |
| `Tools/nw_capture/experimental/decode_in_bodies.py`, `decode_wire_type_ids.py` | frame/record decoding and type-id resolution |
| `Tools/nw_capture/experimental/test_decode_in_bodies.py` | 10 unit tests (varint vectors, framing, records, ids, real fixture) |
| `Tools/nw_capture/experimental/offline/decode_alc_state.py`, `test_decode_alc_state.py` | decode the 63 ALC fields with values out of a capture |
| `Tools/nw_capture/experimental/offline/ghidra/*.java` | headless helpers: `Sweep` (force disassembly + decompile), `DumpAlcSchema`, `DumpStrings`, `DumpQwords` |

Local data (gitignored, `private/decoder-state/`): `nw_positions.csv` and `.json` (765 absolute
samples of the walking test), `trail_clean.json`, `trail_final.json`, `trail_points.json`, and
`ghidra-alc/` with the decompiled schema builder, the name and descriptor dumps, the headless logs and
`alc-fields.json` (the 63-bit table as data).

Captures and logs referenced by the results:

- `Tools/nw_capture/captures/proton_20260910_170118-postal/dtls/ledger.bin` - the walking test ledger
- `Tools/nw_capture/logs/<ts>_pos2.log` - the position samples used for the decode (newest first)
- `Tools/nw_capture/logs/<ts>_postal.log` - the same run's ledger-side log
- earlier: `proton_20260910_154332-writetrace` (write trace), `154811` (read trace), `155107`
  (parse labels), `163227-alcfieldmap` (ALC field map), `165640/165852-walktest`

## Just completed

- **Subagent `a9067196` completed** (NWDB + community map research). Its report is now
  `docs/Network/nwdb-map-research.md` and the durable part is 3.4 of the reference. It settled the axis
  assignment, the region (Windsward, Elin River valley), the working deep link, and that `nwdb.info/map`
  and `newworldminimap.com/map` have no coordinate deep link (their `x`/`y`/`z` are tile indices).
  Its other artifacts stay in `/tmp/nwdb-map/`: `trail.json` (the local player's 204 samples, also
  copied to `private/decoder-state/trail-player.json`), `trail.html`, and `raw/` with the map bundles.
  Lost on reboot and worth refetching rather than rebuilding: `raw/markers.json` (7.4 MB) comes from
  `https://aeternum-map.th.gl/api/markers`.
- A Chrome tab is open on the Aeternum map with the trail drawn (target id prefix `BD87D749`,
  debugging port 9223). The trail there comes from the absolute samples only.

## Next steps, in the order that pays off

1. **Attribute samples to an entity.** The absolute samples mix several entities (the tracker merges
   them by proximity), which is why the trail has gaps and why integrating the `worldPosRel` deltas
   failed: a delta is meaningless until you know whose it is. Fix by correlating probe samples to the
   ledger (cursor -> body offset -> record; the record's V1/V2 tags carry the entity/field identity),
   the same correlation technique used for the earlier probes. Outcome: a continuous trail *and* the
   delta quantisation scale fitted against the absolute anchors.
2. **DONE - the ALC static schema is complete.** The Ghidra run recovered all 63 bits with member
   offset, reader and wire width: the table is 3.2 of the reference. Runtime record decoding uses
   the separate group-0 vector where the trace establishes it; group-1 bit 0 is the only group-1
   entry observed.
3. **DONE - the group-aware record payload decodes.** `decode_alc_state.py` (section 2.4 of the
   reference) reads the group mask, then one field mask and field sequence per active group. It
   reproduces the walking position payload exactly and handles the observed 6..9-byte masks,
   including `scopeInfoBlob` and the other high-bit reader samples.
4. **Settle the last open convention**: the affine mapping of the quantised elevation (the `[-100, 1000]`
   and `1/65535` constants are read in the code, the pairing with the per-entity scale argument is not).
   The north-south question is closed, see 3.4 of the reference.
5. Only then: live map and trail (the original goal) - feed `decode_position.py` output into
   `nw_map_trail.js` on a real-time loop.

## Gotchas that cost time (do not rediscover them)

- `pkill -f "somepattern"` can kill the shell running it when the pattern appears in its own command
  line. Use bracket patterns (`frida[-]server`) and kill by PID.
- Background jobs need `setsid`, otherwise they die when the tool call returns and the capture
  silently covers only part of the test.
- `_runner.py` resolves probe paths against `Tools/nw_capture/`, so pass absolute paths.
- Cursor semantics: the varint reader's cursor read **on leave** is already past the value (first byte
  is `offset - size`); bounded copy reads **on enter** are exact.
- Matching probe events to a ledger by a 16-byte window is ambiguous: require a unique 40-byte window
  or use monotone cursor chains.
- The venv python is required for anything touching the ledger (`lz4` is not in system python).
- Driving the game: keyboard and mouse go to the focused window (`nw_vkeys.py` guards this and
  releases on abort); a virtual gamepad is ignored by SDL when the window is unfocused, and Wine did
  not pick up the uinput pad in this setup.
- Hyprland 0.56 dispatchers are Lua: `hyprctl dispatch 'hl.dsp.focus({window="class:steam_app_1063730"})'`.
- Ghidra: project paths with dot-directories are refused; `.text` has holes inside its nominal span,
  so a wrong VA looks like "no code" instead of an error - check the file bytes.
- Two negative results worth not repeating: there is no float32 reader in the inbound codec, and
  float-looking pairs in bodies are coincidence (0 of 123 candidate slots showed the teleport
  signature).

## Hygiene at the time of writing

The game is running (PID 321407) and must not be restarted; no frida-server process or listener on
27943 survives any run; the repository has no commits for this work yet, only new untracked files.
