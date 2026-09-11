# Resume here

This file preserves the conversation handoff. Continue in
`~/git/personale/new-world-capture`, not the old Aeternum-World checkout.

## User's objective

Capture New World while playing locally on Omarchy or remotely through
Sunshine/Moonlight. Use the shared web app for START/STOP, then eventually decode
live player positioning and show a moving map with a trail.

All documentation, code comments and UI should be English. The user requested
this standalone repository with our tools, documentation, setup and own capture
data, referencing external projects rather than bundling their datasets.
Do not start another workflow for this handoff.

## What is already saved and working

- Capture/Proton tooling, optional local login helper, shared web service,
  video/YouTube integration, offline decoder and checks are in Tools/.
- Local/remote setup: docs/SETUP.md. Web usage: Tools/nw_capture/web/README.md.
- OAuth and recovery: Tools/nw_capture/web/YOUTUBE.md.
- A full capture/unlisted-live/Stop/archive cycle was verified earlier on the old
  deployment. This does not mean the new directory was deployed or live-tested.
- The current archive contains a YouTube link, not the video file. Local backup
  video stays on the gaming host. Do not restore video embedding in the ZIP.
- Our local capture data is copied and gitignored. A private Python environment
  and checksum-verified, gitignored Windows Frida server 17.9.10 are installed.
- External references: docs/REFERENCES.md, including Aeternum-World, First Light,
  NWDB and nw-buddy. Preserve the AGPL license and upstream attribution.

## Completed background work and a correction

Workflow 3b9ee3ed-e143-4adc-9750-c538c5b28fd4 finished and its source/reports were
imported. No pending workflow import remains.

Import review found that its Carrier parser read an explicit two-byte reliable
sequence without advancing the cursor. We added the missing `i += 2` in
Tools/nw_capture/decode_dtls_ledger.py and a regression that failed before the fix
and passed afterward. Both saved captures were rerun. **The workflow's original
numeric results are superseded by the reports in this repository.** Do not
resynchronize the old decoder over this corrected one.

Current evidence:

- docs/Network/offline-position-proof.md
- docs/Network/hive-capture-position-proof.md
- private/hive-workflow-import.json (source and corrected-file hashes)
- private/hive-post-import-diagnostic.json (aggregate external comparison)
- Tools/nw_capture/captures/offline-position-scratch/new-workspace-diagnostic.json

## What the other capture taught us

The external Hive capture has four separate connection windows. Each channel-1
sequence starts at zero and is continuous within that window; combining windows
had produced false order errors. Chunk reassembly completes without observed
countdown/sequence errors in those streams.

It provides cleaner sequence evidence than our Test teleport capture, which has
11 sequence gaps/order breaks. However, cleaner sequences did not validate our
application framing hypothesis: most application bytes remain unresolved.
We must not assume that simply collecting more traffic will resolve the schema.

Corrected results:

| Observation | Hive | Our Test teleport |
|---|---:|---:|
| Ledger records | 40,254 | 6,354 |
| Parsed Carrier messages | 78,799 | 11,923 |
| Reassembled IN ch1 pieces | 25,768 | 4,120 |
| Varint-length application candidates | 258 | 421 |
| Unresolved application bytes | 3,366,723 | 1,127,682 |

These are bounded parsing candidates, not verified gameplay messages. Hive's two
marker-like candidates fail exact consumption (`payload_leftover`). Our capture's
881 marker-like matches fail `has_sequence_invalid`. No exact StateBundle or inner
member boundary is verified. Positions, player identity, rotation, equipment
changes and local-player ownership remain undecoded. Type-13/coordinate parsing
is not attempted, not a measured absence of positions in the traffic.

## Next technical step

Resolve actual application stream framing and the type-8 body using the matching
client's deserializer. Account for unresolved Carrier tails and sequence gaps.
Treat First Light's notes and the static catalog as references, not an authoritative
schema for this build. Do not scan arbitrary floats and present them as a trail.
Only add the live map after coordinates and local-player attribution are validated
against recorded movement/teleport evidence.

## Reproduce our offline check

From the new repository root:

```sh
.venv-capture/bin/python Tools/nw_capture/experimental/offline/test_decode_saved_position.py
.venv-capture/bin/python Tools/nw_capture/experimental/offline/decode_saved_position.py \
  Tools/nw_capture/captures/offline-position-scratch/ledger.bin \
  --out-json Tools/nw_capture/captures/offline-position-scratch/new-workspace-diagnostic.json
```

After import/correction, the offline regression, both ledger reruns, 15 capture
Python tests, 8 web Python tests, both Node lifecycle modes, OAuth checks and Python
compilation passed. README.md contains the runnable checks. Live gameplay decoding,
a coordinate plot and a new deployment were not verified.

## What was intentionally not moved

The other user's Hive RAR/ledger, Catalog/game dumps, First Light checkout,
upstream raw logs and host OAuth/SSH/Steam credentials are not bundled here.
The Hive ledger remains in the old workspace's
Tools/nw_capture/captures/offline-hive-scratch/ directory and was read there only.
Own captures and private aggregate results are local, gitignored and not backed up
by Git. Do not delete the original workspace or remote deployment during handoff.

The existing game, streaming host, tunnel and capture service were not restarted
or relocated. Old host paths in historical setup notes still describe that live
deployment. Switching deployment is a separate operator-controlled step after
capture stops and owned-worker cleanup is verified.

This is a local Git repository on main, with no remote or initial commit as of
this handoff. Files are saved on disk, not pushed or externally backed up. Check
Git status and review the source-only file set before committing or publishing.

## Update 2026-09-10: repository published privately

The wording above describing an uncommitted, unpushed repository is historical.
Current state:

- `main` has initial commit `45bed3c`, 52 files, source and docs only.
- Remote: private `vekexasia/nwc` (https://github.com/vekexasia/nwc),
  `main` tracks `origin/main` and is in sync.
- Live host details were redacted before the first commit: `62.210.248.2` ->
  `YOUR_GAMING_HOST`, the client public IPv4 -> `YOUR_CLIENT_IP`, the SSH host key
  fingerprint removed, `/home/andrea/...` -> `~/...`.
- Real values live in the gitignored `.env`; `.env.example` documents the keys.
  Neither the captures nor `private/` nor the Frida server binary are tracked.
- Commit identity is set in this repository only, to the GitHub noreply address.

The technical next step further down is unchanged.

## Update 2026-09-10 (second): the player position is decoded

The lines above saying that positions, rotation and type-13/coordinate parsing remain undecoded,
and the "Next technical step" section, are historical. The inbound application records are now
decoded through the registry's `ALCReplicatedState` type (typeIndex 11) on our own capture, and the
two position fields are read from the wire.

What is verified:

- The frame and record layers are consumed exactly (the type reference resolves 11,858 of 11,858 in
  a live run) and the ledger bytes line up with the reader cursors.
- `worldPosAbs` (`0x142a433d0`, 10 bytes: two big-endian float32 plus a quantised u16 in
  `[-100, 1000]`) and `worldPosRel` (`0x142a43330`, three quantised deltas, `0xff` = no update) are
  hooked in the running client; driving two 4 s walks produced a monotonic track
  (`x 8786.66 -> 8893.83`, second float `3003.97 -> 3126.63`, elevation `58.03 -> 74.35`).
- The axis assignment is confirmed against the community marker set (55739 markers): with the
  first float as east and the second as north the decoded positions sit a median of 16.6 units from
  the nearest recorded marker with a median elevation error of 1.38, swapped 781 units. The track is
  in Windsward, along the Elin River valley.

Still not decoded or not verified: local-player identity and ownership (the current track is
separated heuristically by monotonicity and proximity, not by an identity field), the semantics of
rotation and look direction, equipment changes, the semantics of the ~14 ALC fields, group-1 entries
beyond bit 0, the affine mapping of the quantised elevation, and an overlay on the map image from a
plain page (drawing into the live page works).

Documentation in reading order: `docs/Network/alc-protocol-reference.md` (the reference),
`alc-static-analysis.md` and `alc-runtime-fieldmap.md` (the raw reports),
`offline-framing-findings.md` (the research log), `position-decoder-plan.md` (the plan),
`decoder-state.md` (resume snapshot) and `nwdb-map-research.md` (coordinate convention and deep
links).

Reproduce:

```sh
# capture while probing exactly the two position readers
.venv-capture/bin/python Tools/nw_capture/experimental/nw_capture_probe.py \
    --probe "$PWD/Tools/nw_capture/experimental/nw_pos_probe.js" --seconds 60 --label pos
# the same, driving the character (needs the game focused; the tool guards and restores focus)
.venv-capture/bin/python Tools/nw_capture/experimental/nw_walktest.py \
    --seq "w:4,release:12,w:4,release:12" --wait-focus 120
# decode the resulting log, then draw it on the map
.venv-capture/bin/python Tools/nw_capture/experimental/decode_position.py \
    --log Tools/nw_capture/logs/<run>_pos_samples.log --csv /tmp/pos.csv --json /tmp/pos.json
```

Map: `https://aeternum-map.th.gl/?x=8800&y=3060&zoom=6` (all three parameters are required), and
`Tools/nw_capture/experimental/nw_map_trail.js` to draw the decoded points into the live page.

Current next technical step, replacing the one above:

1. The group-aware ALC record payload and 1..9-byte mask reader are implemented and documented in
   `docs/Network/alc-protocol-reference.md` section 2.4. The trace maps group 0 where its bits were
   set and group-1 bit 0; the remaining group-1 entries are not evidenced.
2. Attribute samples to an entity (record context, not proximity) so the trail is continuous and
   the `worldPosRel` delta scale can be fitted against the absolute anchors.
3. Only then the live map and trail.

## Update 2026-09-11: the player's health is decoded from the traffic

The Vitals state (typeIndex 15) is no longer a static table only: the payload model and the value are
verified against the game's own numbers.

What is verified:

- The payload has **no opcode**. For each member that changed, in the state's member order, the reader
  `0x17b4110` reads `[member mask][field mask][fields]`, consumes the fields of every set bit, then
  moves to the next member. `01 01 <f32>` is member 0 with field bit 0; `01 09 <f32> <1B>` is member 0
  with field bits 0 and 3.
- Member 0 is `+0x7c0` (`HealthAmount`) and its field bit 0 is a **big-endian float32**. Draining the
  player's own health with the right mouse button produced deltas of exactly **+57.7** and **-362.4**,
  the `+57` heal and `362` damage the game printed on screen.
- The member order is the registration order in `FUN_14671E040`: 0 `+0x7c0`, 1 `+0x7e8`, 2 `+0x810`,
  then `replicatedAfflictionsHotData` `+0x970`, `replicatedAfflictionsColdData` `+0xc18`, `vitalsData`
  `+0xec0`, `healthChangeFlags` `+0x928`, six unnamed `0x28`-byte structures at `+0x838`..`+0x900`, and
  `vitalsId`, `vitalsCategoryId`, `vitalsLevel`, `invulnerability`, `displayImmuneWhenInvulnerable`,
  `maxHealth`.
- Reproduced on a second, independent capture: five `-362.4` drops inside the `drain_start`/`drain_end`
  window, with +57.7 and +43.9 between them, then steady regeneration. An 85-second capture gave 3140
  Vitals payloads over 121 objects, which is enough for a tailing live readout.

Still open: the field mask bits of member 0 other than bit 0 and of every member after member 0 (that
is what stamina and mana need), how the non-health amounts encode their value (a sprint-correlated
payload is not a plain float32), the reader's delta stage (varint plus member vtable `+0x50`), and
attribution of an object to the local player without the combat text, since the object pointer changes
on every launch.

Reproduce, from `~/git/personale/new-world-capture`:

```sh
# capture (no focus, no input) while the state is read; the probe records object, bytes and payload
.venv-capture/bin/python Tools/nw_capture/experimental/nw_capture_probe.py \
    --probe "$PWD/Tools/nw_capture/experimental/nw_state_probe.js" --seconds 85 --label vitals3
# in parallel, a timed action sequence (this part takes the focus and restores it)
.venv-capture/bin/python Tools/nw_capture/experimental/nw_actions.py
# read the health out of the log; --check runs the self-check
.venv-capture/bin/python Tools/nw_capture/experimental/offline/decode_vitals.py \
    --log Tools/nw_capture/logs/<run>_vitals3.log --object <addr>
```

Reading order for this part: `docs/Network/decoder-state.md` (the health section),
`health-field.md` (the 19-member static table), `replicated-state-todo.md` (the per-state TODO and the
working loop).

Current next technical step: the field mask bits of members 1..18, member by member. What is already
settled on the way there is member 1; the earlier attempt with a corrected action sequence (spells on
Q, R and F) gave a float32 in `[0, 100]`, but the object it came from was the one identified by a
health drain, which is not established. The dedicated mana capture below replaces that evidence.
Two questions were open at that point and are now closed: whether the injected keyboard reaches the
game at all, and where stamina lives.
That is **not** an input problem: injected keyboard input does reach the game. Injecting `m` through
the same uinput device that the action sequence uses opens the map, which is visible in a `grim`
screenshot of the game window before and after. Spells also work inside a settlement, and **member 1
(`+0x7e8`), field bit 0, is the mana**: a
float32 `[0, 100]`. Verified on `proton_20260911_092010-mana` (idle, Q, R, F, idle) by two independent
channels - the ability cooldowns on screen (`19` -> `17`/`15` -> `14`/`12`/`8`) prove the casts fired,
and the object `0x5724afd0` sends no mana update before the first one (full, because the client sends
a field only on change), then `77.5` after Q and `55.5` after R - while a blue bar on screen goes from
130 to 97 pixels, ratio `0.75` against the decoded `0.72`. Caveat: in the "before" screenshot that bar
is not drawn, so the full end is inferred from the missing updates, and the pixel check is one ratio,
not a series. An earlier `64.10` figure came from an object identified by a health drain and is
dropped.

**Shift is the dodge**, not sprint, so the earlier "sprint" phases were a run with one dodge in them.
That is where stamina went, and stamina is not a Vitals field at all: it is ALC `group0.bit37`, a half
float carrying the missing **segments** as a negative deficit that returns to exactly `0`. Evidence: the
capture `proton_20260911_091552-dodge` (30 s, idle around one shift tap) has `bit37` **zero times
before the dodge and thirteen times after**, reading `-4.0`, `-2.0`, `0.0`; the drain capture reads
`-5.0` -> `0.0` and the action capture `0.0` -> `-7.0` -> `-5.0` -> `0.0`. That closes the third player
number, after health and mana.

Also to re-check: the earlier captures interpreted the health drops as the player's own right-mouse
drain. If the character was in a settlement then too, the ability cannot have fired, and the drops
were ordinary damage from something else. The numbers matched what the game printed on screen, and
that is what validates the decode; the mechanism that caused them is an interpretation, not evidence.

## Update 2026-09-11 (last): PlayerComponent is decoded, and it carries the names

The identity state was the Tier 1 gap. Its unmarshal (`0x6573d60`) is four lines and calls a builder,
`FUN_146711e90`, which registers **31 fields with real names**: `characterId` (`+0x7c0`),
`characterName` (`+0x870`), `homeWorldId` (`+0x8f0`), `srcWorldId`, `platformAccountId`, `playerType`,
`loginMatchId`, and a set of account/store/transmog flags. Registration order is the member order, as
for Vitals, and the same three-stage deserialiser (`FUN_146160ae0`) reads them.

Verified live: `Tools/nw_capture/experimental/nw_player_probe.js` hooks the builder and reads the
fields 150 ms later; a 20 second capture saw 21 PlayerComponent states and the character names came out
as real names (`stormvind`, `Warrior3`, `Eins Fas ttv`). Three of our field names also line up with the
community's independent decode of a spawn body (`character_name`, `player_type`, `platform_account_id`).

What is still open, and it is the whole of the remaining attribution problem: the **type and width of
each field** (the id fields are structures, not integers) and the **link between a PlayerComponent and
the ALC/Vitals states of the same entity** - the replica id is in the bundle header, so the join has to
come from the bundle order at runtime or from a shared field. Full table and method:
`docs/Network/player-component.md`.
