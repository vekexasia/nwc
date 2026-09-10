# Plan: get one verified player position out of an offline ledger

Goal: decode a real player position (x, y, z) from a capture we already have, offline,
without launching the game. Live position streaming and the map are explicitly out of
scope here.

Rule for this plan: **stop at the first success**. The steps are ordered cheapest first,
each has an explicit success criterion; when one is met, stop and report. Do not continue
to later steps, do not generalise to full message coverage, do not start the live feature.

Results so far are in [offline-framing-findings.md](offline-framing-findings.md): S1 succeeded
(frame confirmed for 96% of channel-1 messages in the teleport ledger), S2 did not (no wire
value resolves in the private registries).

Baseline to beat (from `offline-position-proof.md`): 1,127,682 unresolved application
bytes, 421 bounded candidates, 881 StateBundle attempts all rejected by
`has_sequence_invalid`, zero verified positions.

## External scale reference

Note: the baseline above predates the position result. The field is now decoded and verified; see
[decoder-state.md](decoder-state.md). What follows is kept as an independent cross-check of framing
completeness, not as evidence about whether we can read the field at all.

ratbuddy publishes a retail-vs-current-build replication diff (`traffic-spectrum-diff`, 2026-09-10)
that bins channel-1 server-to-client StateBundle traffic per frame and counts, among other metrics,
`records` (decoded StateBundle records), `alc_rows`, `abs_rows` (ALC rows carrying `world_pos.abs`),
`action_rows` (`slayer_state_id[0]`) and `sequence_only_rows`. Retail per-bin maxima in its published
source summary range 14-30 for `action_rows`, 10-32 for `abs_rows` and 0-2 for `full_keyframes`.

Use those as a scale check on our own ledger: if our per-bin `records` or `abs_rows` counts sit far
below the retail envelope on a movement capture, the framing is still incomplete even though the
position reads. The reports are aggregate metrics from someone else's corpus and build, and their
underlying databases are internal, so cite them and do not copy the tables here. See
[REFERENCES.md](../REFERENCES.md). The same source independently names `world_pos.abs` inside ALC
rows, corroborating the field name and container in [alc-static-analysis.md](alc-static-analysis.md).

Same source, bounded negative: the companion `/completeness/` ledger tracks 1583 checklist items
over a 235-capture corpus and holds no position, transform or rotation entry; its movement tab
contains five local input items and seven unscanned swimming items. Positions were not tracked as a
work item in that corpus, which is consistent with this field having to be recovered from our own
capture and static analysis.

Also worth measuring rather than assuming: the published retail `payload max` is 1115 bytes for
almost every source, with p95 equal to the max, which suggests a hard cap on the channel-1 payload
per bin. Check whether our own per-bin payload maximum also stops at 1115; if it does, that is a
transport constraint, not a codec property.

## What the private attachments actually provide

Verified by inspection of `private/open-world-discord/attachments/`:

- `087_typeregistry.json`: 3487 entries, each with `name`, `uuid`, `index`, `typeIndex` and
  a `handler` of real addresses (`Marshal`, `Unmarshal`, `CreateInstance`, ...).
  `index` is dense `0..3486`; `typeIndex` is sparse `0..7051`. No entry is named
  `*ReplicatedState`, and only 2 of 3487 uuids exist in `serialize.json`.
- `128_serialize.json`: `uuidMap` with 4362 entries carrying `name`, `factory`/`serializer`
  addresses, `azRtti` hierarchy and `elements[]` (field name, `nameCrc`, `typeId`, `offset`,
  `dataSize`) - i.e. field layouts, but for the AZ reflection registry, **not** for the
  network types. `classNameToUuid` has 7156 `[hash, uuid]` pairs, `enumData` 326 enums.

So the type table exists (names plus a dense u16-sized index, plausibly the wire `type_idx`),
field layouts for the network types do **not** exist in these dumps and have to come from
the binary or from the wire itself. The reported `3410+` message types to handle match the
3487 entries of the registry.

## Steps

### S1 - Framing: replace the guessed marker with the reported one

Method: the community reports that the first 4 bytes of a Message V3 payload are the
signature `0x970C0A5D`, and that a 4-byte prefix precedes the LZ4 stream. Our decoder uses
`STANDARD_MARKER = 00 01 08 01` and a 2-byte compressor header. Add a small read-only
scanner over the existing ledger (`captures/offline-position-scratch/ledger.bin`) that
counts occurrences of both candidates at candidate offsets and reports, per candidate,
how many channel-1 messages become fully consumed. No behaviour change to the existing
decoder until the numbers say so.

Success: at least one application message consumes every byte it claims (full consumption
count > 0), i.e. the framing hypothesis produces a closed message, not another bounded
prefix. Cost: hours, offline.

### S2 - Type table: `index` -> name, applied to our own RSB

Method: build `index -> {name, uuid, typeIndex}` from `typeregistry.json`, then dump the
actual `type_idx` values our decoder sees inside a ReplicatedStateBundle and check them
against the table (range, density, plausible names for the states we can already
partially decode). Distinguish plainly between "the table plausibly matches" and
"the table is confirmed".

Success (weak, but decisive for direction): every `type_idx` observed in a bundle resolves
to a name in the table, and the states we can already see partially get names that are
consistent with what they do. Cost: hours, offline.

### S3 - Field layout for exactly one state

Method: pick the single state that carries the player position (per the community: ALC
create carries world position, player entities have no `PositionInTheWorldReplicatedState`).
Get its wire layout from the `Unmarshal` address in `typeregistry.json` (`NewWorld+0x...`,
image base `0x140000000`), with `AzSerializeContextRenamer.java` and
`AzModuleComponentDescriptorRenamer.java` applied, and cross-check against the idx-8
`message.txt` dumps in the attachments. Round-trip against real capture bytes.

Success: one member decodes completely and re-encodes byte-identical. Cost: a day or more,
offline, needs Ghidra.

### S4 - Position from the teleport ledger

Method: apply S3 to `captures/offline-position-scratch/ledger.bin`, look for coordinates
that change consistently with the known teleport, and check plausibility against the map
region.

Success: x, y, z that move with the teleport and land in a plausible region for the local
player. Cost: a day.

### S5 - Only if S4 is ambiguous

Method: capture a second session with a known landmark and movement segment, correlate.
Requires launching the game, so it is last. Success: the coordinate stream correlates with
two known landmarks. Cost: a session plus analysis.

## Rules while executing

- Offline only: no game launch, no live capture, no cloud, no changes to the web service.
- Scratch tools and diagnostics belong in `Tools/nw_capture/experimental/`, thin and
  self-contained; the private attachments stay in `private/` (gitignored).
- Every claimed wire field needs an evidence pointer: an IDA/Ghidra address, a capture
  offset, or a cited line in the Discord notes. No "looks right".
- The community dumps come from someone else's build: before trusting any layout, confirm
  at least one already-identified name against our own capture.
- Do not touch the vendored/third-party binaries; the codegen exe stays unused unless S3
  needs it.
- Any workflow used for this runs foreground, no budget limits, script written to `/tmp` and
  opened for operator review first.
