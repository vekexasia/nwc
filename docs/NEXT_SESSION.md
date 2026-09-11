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

## Update 2026-09-11: injecting input without stealing the desktop, what works and what broke

Goal: run the action sequence without the focus flicker on the user's screen. Two routes were tried.

**1. An output headless in Hyprland (rejected, but for a fixable reason).** On Hyprland 0.56 the
classic dispatchers are gone: `hl.dsp.*` builds a *closure* that must be passed to `hl.dispatch`, which
is why `hyprctl eval 'hl.dsp.window.move{...}'` answers `ok` and does nothing. The working call is

```sh
hyprctl dispatch 'hl.dsp.window.move({ window = "address:0x…", monitor = "nw-headless", follow = false })'
```

With a dummy output (`hyprctl output create headless nw-headless`) and the game moved onto it, an
injected `m` **did** reach the game: the map opened, confirmed by `grim -o nw-headless`, while the
physical monitor kept showing the user's desktop.

**But this does not solve the actual problem.** Keyboard focus is exclusive: feeding the game at the
device level means the user loses the keyboard for those seconds, and that is exactly what happened -
the user felt the focus being taken. The dummy output hides the game, it does not stop the focus theft.
Any device-level injection steals the focus by construction; only injecting **above** the device would
not, and that route is the dead end below. Do not describe this as "input without stealing the desktop"
again.

What broke is the **side effect of creating the output**: Hyprland 0.56 redistributed workspaces onto
the new monitor, which moved 17 of the user's windows to a workspace they did not belong to and made
the desktop look rearranged. All of them were moved back by hand. If this route is ever revisited, pin
the user's workspaces first with explicit `workspace = N, monitor:HDMI-A-2` rules, so a new output
cannot claim them.

**2. Driving the action layer directly (dead end, for now).** The action names are in the binary
(`Sprint` at `0x1480782dc`, `Sprint_Start`, `Dodge` at `0x1480782f8`) but Ghidra finds **no code xref**
to any of them, and a read-only scan of every writable memory range found **no pointer** to those
strings either. So the runtime action objects do not reference the name strings, and the user-facing
names are presumably keyed by something else (hash or a table). The route would need another entry
point; it is not a matter of calling a function found by name.

The input path itself is also structurally hostile to synthetic events: the game imports
`GetRawInputData`, so `PostMessage` style events are ignored, and under Proton raw input only flows to
the focused window, which is why focus has been needed at all.

## Update 2026-09-11: the live view during a capture

`Tools/nw_capture/experimental/nw_live.py` follows a probe log (or a directory of them, picking up each
new capture on its own) and serves what it decodes:

```sh
# capture with the probe that now logs position, Vitals and player names
.venv-capture/bin/python Tools/nw_capture/experimental/nw_capture_probe.py \
    --probe "$PWD/Tools/nw_capture/experimental/nw_state_probe.js" --seconds 60 --label live
# in another terminal, follow the log directory and open the page
.venv-capture/bin/python Tools/nw_capture/experimental/nw_live.py \
    --log Tools/nw_capture/logs --port 8765
```

The page draws a trail per object on a canvas and a table of health, mana, position and name, polling
`/state` every 250 ms. Verified live: two samples during a capture grew from 570 to 789 position
samples and 423 to 817 health samples with a last-line age of about one second.

Three honest limits, all visible in the page rather than hidden:

- **It cannot say which object is you.** Position (ALC), health and mana (Vitals) and the names
  (PlayerComponent) are three different objects with no common key; the replica id is in the bundle
  header. The page lets the user pick the object once and keeps it in localStorage.
- **Names are provisional.** The name is read from `field + 0x10` up to the first non-printable byte,
  because the field's type is not decoded; some objects show a plausible name (`SirChaos`) and some
  show junk or nothing.
- **Elevation is reported as `elev_raw`,** the quantised u16 as it comes off the wire: the affine
  mapping back to world units is not established, and calling it an elevation would be a guess.

`decode_vitals.py` now exposes `parse_members()` and the offline reader uses the same function, so the
live view cannot drift from the verified payload model. Stamina is not in the live view yet: it is ALC
`group0.bit37` and comes from the ledger, whose frames are not joined to an entity either - it needs
the same join as the attribution above.

## Update 2026-09-11 (later): the player is identified by walking, and what blocks the join

The manual object picker in the live page was a stopgap and it read as one. It is gone: the page has a
single button, and the server watches the next three seconds of movement, picks the object that moved
most, and reports the distance and how many times it beat the next candidate. If nothing moved it keeps
the previous answer and says so. The arithmetic is covered by `nw_live.py --check` with synthetic
positions (picker object, distance, margin, quiet window).

That identifies the **position** object. The health, mana and name live in **different** objects, so
they stay unattributed until the record join lands, which is still the open item.

What was learned while trying the join, so the next session does not redo it: the record-layer readers
already used by `nw_record_probe.js` take their context as the **fourth** argument (decompiled at
`FUN_146af20d0` for the V1 varint at `0x6af2134`: `FUN_14087b5c0(dst, a, b, *param_1)`, and at
`FUN_1461acfe0` for the type reference at `0x61ad00f`). Attaching the current record to state reads with
those hooks produced a **constant** value across a hundred different states, so the cursor offset used
(`ctx + 0x10`, the one the ALC field readers use) is wrong for these readers: the tracker was removed
rather than left in the log as a lie. The next step there is to read the decompiled bodies around those
call sites and find where the varint value actually lands.

Also on this machine, after the failed attempts: tbe attach chain gets stuck (`frida.TransportError:
timeout`, and before that `frida-agent.dll: File exists` inside the Proton prefix, which was a leftover
temp directory that was cleaned). Three consecutive captures failed to attach after that, which points
at a stale instrument inside the running game process: restarting the game is the usual fix.

## Update 2026-09-11: why the attach to the game times out, and the rule that was missing

Symptom: every capture failed with `frida.TransportError: timeout was reached` on attaching to
`NewWorld.exe`, while the same frida-server still worked.

What the diagnosis showed:

- The device was fine: `device.enumerate_processes()` listed 14 processes, and attaching to
  `services.exe` in that same device succeeded in **0.0 s**.
- Attaching to `NewWorld.exe` timed out at 25 s, with `realm="native"` and with `realm="emulated"`.
- `/proc/<host pid>/maps` of the game process contains

  ```
  .../AppData/Local/Temp/re.frida.server/x86_64/frida-agent.dll (deleted)
  ```

  i.e. an agent from an earlier session is **still mapped inside the game process** and the file it was
  mapped from no longer exists.

Cause, and it was self-inflicted: an earlier attempt failed with `frida-agent.dll: File exists`
(the leftover agent file blocked the server). Instead of stopping there, the temp directory
`re.frida.server` inside the Proton prefix was deleted, which **unlinked the file of a mapped DLL**.
From then on Frida cannot inject a new agent into that process: the orphan holds the channel and the
25 s handshake never completes.

**Rules that follow, and were missing:**

- Never delete `.../AppData/Local/Temp/re.frida.server` while a session may still be live: the agent
  stays inside the game process until the game restarts, and unlinking its file makes the process
  permanently unattachable.
- Never kill a frida-server while a capture session is live: that is what orphans the agent. One
  capture at a time, and stop it through the tool.
- If a capture fails with `frida-agent.dll: File exists`, the fix is **restarting the game**, not
  cleaning the prefix. The in-process agent cannot be unloaded from outside.

The capture tool now refuses to start in that state instead of timing out: it reads `/proc/<pid>/maps`
of every `NewWorld.exe` host process, and if a `frida-agent` mapping is there (with the capture lock
held, so no other capture can be the owner) it prints the host pid, the reason and the fix, and exits
with code 3. The check is exercised by every capture and does not match its own command line, because
it matches on the process name rather than on a command-line pattern.

## Update 2026-09-11: the entity join is done, V1 is the entity and V1 = 1 is the player

The "record join" blocked above is resolved, by reading the record reader instead of guessing the
cursor offset: `FUN_146af20d0` reads V1 into a u16 out parameter (args[1]), a u8 chunk count (the old
"constant 0x01") and then `FUN_146af2340` per chunk (V2, type reference, factory, unmarshal, push
`{V2, object}`). The varint primitives return their value behind **args[2]**; the failed attempt read
args[0]. Reference: `docs/Network/entity-join.md`.

Verified live (three 40 s captures and one 4 s driven walk): V1 groups ALC, Vitals, DamageReceiver,
Paperdoll and the rest of one entity, with coherent tracks and plausible health; V2 is the chunk slot;
the object pointer on the vector is transient and never was an entity key; **the entity that moved
only during the injected walk is V1 = 1**, which is also the first record of every body in all four
captures and the only entity with the owner-only states. Every ALC payload decodes exactly against the
chunk length measured by the hook, and that measurement gives the payload length of every type
(record-length oracle) for free.

Tools: `Tools/nw_capture/experimental/nw_join_probe.js` (emits `join_samples` plus the `pos_samples`,
`vitals_samples` and `player_samples` shapes `nw_live.py` already reads, keyed `e<V1>`), and
`Tools/nw_capture/experimental/offline/decode_join.py` (`--check` passes). With the join probe as the
running capture, the existing live page showed `e158 "Where Arda" health 18708 + position` and
`e220 "Vadi G"` joined, and `e1` as the player, with no change to `nw_live.py`.

Coordination note: two agents worked on this tree today. `nw_capture_probe.py` now kills leftover
frida-servers only after taking the capture lock (a leftover found before the lock was the other
capture's live server). Captures serialise on `/tmp/nw-capture.lock`; wait for it, do not clear it.

The pose needs no extra hook: the `slayer*` fields are inside the ALC payload the join probe already
logs, and `decode_join.py --timeline 1` (from a join log, or `--ledger` from any old capture whose
stream frames) prints the player's state machine. First rows of the table, from one walk and the
`actions2` run: `0x1a` walking, `0x1b` stopping, `0x1f` idle, `0x2d` cast/hit
(`docs/Network/pose-state.md`).

Next, in order: (1) make the live view default "me" to `e1` and keep the V1 -> name map for the
session (names arrive once, at scope entry); (2) one action per capture with the join probe
(jump, dodge, attacks, weapon draw, mount) to fill the pose table; (3) the ALC encoder with a
decode -> encode -> identical-bytes round trip over the captured chunks.

## Update 2026-09-11 (later): live view joined, pose table started, encoder proved

Done in this pass, one agent per file set so nothing collided (captures only from the main agent):

- Live view (`nw_live.py`, `--check` passes): with entity keys `me` defaults to `e1`
  (`join-default`), a manual walk/pick still wins, and a log rotation keeps names and values. Verified
  live on port 8769 with a join capture: ten named players with health and position, `e1` as player.
- Pose (`docs/Network/pose-state.md`): `decode_join.py --timeline 1` keeps the four slayer layers
  apart. Two driven captures name the states: L0 idle `0x1f`, walk `0x1a`, run `0x0d`, dodge `0x0b`,
  sprint `0x07`, stop `0x1b`, jump `0x0e`; L1 weapon draw `0x2c`, ready `0x2d`, light attack `0x21`,
  heavy `0x27`, RMB ability `0x24`; L2 `0x2e` only during attacks. Values are still printed as raw
  prefix-varint hex.
- Encoder (`offline/encode_alc_state.py --check`): mask/prefix varints, grouped field framing and
  record header re-encode 65,724 of 65,771 captured ALC chunks byte-identical (the 47 others are the
  ones the decoder cannot consume exactly) and all 10,564 record headers of a ledger. Two prefix
  varints on the wire were longer than minimal.
- Framing (`docs/Network/ledger-framing-gaps.md`): jump and dodge ledgers do frame; the 10:57 walktest
  stream opens inside a 1.9 MB message that never completes in the capture, so nothing frames. No
  decoder change.

Next: (1) decode the prefix-varint values in the pose timeline as integers; (2) block, sheathe,
mount, swim, and the same actions with a second weapon (are L1 ids per weapon?); (3) the asset side,
`slayerStateId` -> slayer script -> clip via nw-buddy; (4) frame/Carrier/DTLS encoders on top of the
record encoder, then the heartbeat server, only with explicit authorization.

## Update 2026-09-11 (evening): the viewer got its factors, and two states the wire does carry

Corrections to earlier claims in this file: **stamina is on the wire** (`StaminaComponentReplicatedState`
4297, six f32 BE fields, 60 Hz while it moves) and **cooldowns are on the wire**
(`CooldownTimersComponentReplicatedState` 2932: per slot id, revision, expiry and start in microseconds
since 2000-01-01 UTC). Both were in our join logs all along; the community catalog
(`capture-triage.html`) is where to look first for "which state carries X". `serialize.json` does not
list replicated states, only components and their asset/config fields.

Live viewer (`nw_live.py` / `nw_live.html`, paper style, pan/zoom/follow, reset, mobile layout): position,
names, health (max = highest seen, kept in `/tmp/nwc/nw_live_max.json`), mana, stamina with `winded`
and `regen delay`, cooldown slots, pose label (ALC slayer ids, layers 0 and 1), facing wedge (ALC
`rotation`, smallest-three quaternion, heading = yaw + 90), elevation in metres, damage feed from the
Vitals deltas. Tiles were one tile too far south before today; fixed against aeternum-map's
`getTileUrl`. Checklist and what is blocked: `docs/Network/live-viewer-todo.md` (mob names and
equipment need the item/spawn datasheets; HealthMax is not replicated; mount flag awaits one driven
mount).

Operational: a background capture ignores SIGINT (shell background jobs), so a running capture cannot
be stopped early without orphaning the Frida agent; wait for its timeout or restart the game. `pkill
-f` with a pattern that appears in the calling command line kills the caller: bracket one character.

## Update 2026-09-11 (night): the name book, and the wire ids are crc32 of the datasheet ids

The big unlock of the day: **every opaque u32 id on the wire is the CRC32 of the lowercase datasheet id
string.** All seven cooldown ids resolved to weapon abilities on the first try (`Ability_VoidGauntlet_Scream`
= `9d35d4b6`), then mounts (`Mount_MTX_bear_Panda`), equipped perks (AbilityComponent 185), items worn
(Paperdoll 3183: `2hGreatAxeLostT5` = Forsaken Great Axe), status effects (4236: Miner's Resolve),
and the vitals row of every mob (Vitals full state: Black Boar, Grey Wolf, Withered Punisher).

Tools, all under `Tools/nw_assets/`:
- `pak_extract.py`: list/extract entries of the game's .pak (zip; method 15 = Oodle). The Oodle
  decompressor is third-party and lives in `private/tools/oodle/liboo2corelinux64.so.9` (gitignored).
- `datasheet.py`: the binary datasheet reader (new-world-tools layout), checked on mounttypes.
- `namebook.py build`: extracts the 2,250 datatables (215 MB) and the 184 English localization files
  into `private/assets/`, writes `private/assets/namebook.json`: 265,451 ids, 102,479 with English text.
  `namebook.py lookup HEX...` resolves ids. `nw_live.py` loads the book at start; a 4-byte window scan
  filtered by sheet is how Paperdoll/StatusEffects/Vitals ids are read today (no field tables yet).

Also decoded today, all in the live view: stamina (4297), cooldowns (2932), mount (5620, driven),
level (899), faction (3152: 1 Syndicate, 2 Marauders, 3 Covenant per javelindata_factiondata), mana
(1652), player vs companion (Vitals member 0 bit 1), stance byte (ALC group0.bit43), facing (ALC
rotation quaternion), static positions (13) for camps and nodes, Interact flag (2930). Captures start
and stop from the page (`/capture/start`, `/capture/stop`, SIGINT restored in the child).

What did not fall: the numeric slayer state ids (pose) have no table in binary or assets
(`docs/Network/pose-state-names.md`, a subagent's full pass); the mapping is runtime-generated. The
driven table in `pose-state.md` and the player's own reports from the page remain the way.

Encoders proven byte-exact: ALC payload (`encode_alc_state.py`), record and frame
(`encode_record.py`, 9,365 frames). Next on the replica path: Carrier and DTLS.

Later the same night: Carrier encoder proven (`encode_carrier.py`: uncompressed datagrams byte-identical,
LZ4 ones stream-identical after decompression; lz4.block.compress matches the original bytes for a
quarter only, so the writer emits mode 0x80). The encoder stack below the replica is now ALC, record,
frame, Carrier; DTLS is the last layer and the first one that talks to a real client, so it stays
gated on explicit authorization. `nw_rmi_probe.js` (census of every type reference, bytes after the
watched client-facet RMIs such as OnDamageDealt 2071) is written and untested: the game was off.
Pose additions: L3 0x20 = dead, L2 0x2e = attacking, L0 0x09 gathering, L1 0x29 fishing, stance byte;
L0 0x18 (entered from stopping/idle, speed 0, mount-independent) is still unnamed, candidates
TurnInPlace / IdlePoseTrans from the CAGE aliases.

The live server follows Tools/nw_capture/logs on port 8769; start a capture from the page when the
game is back (`start capture`), then run `nw_rmi_probe.js` once through nw_capture_probe.py for the
RMI census (it needs its own capture slot: one Frida session at a time).

## Update 2026-09-11 (20:20): the game is back, RMIs and chat

- `nw_join_probe.js` now also emits `rmi_samples`: every typed message that is not a state chunk, with
  the bytes after the type reference. `decode_rmi.py --log` lists them by catalog name; a 60 s
  standalone run saw 51 types. Client-facet RMIs start with the 16-byte target uuid.
- **Chat decoded** (`ReceiveChatMessage` 4118 and the batched 293): sender uuid string, name, six bytes
  (channel), text, Steam id. Shown above the damage feed. Per-hit damage RMIs (2071, 3601) will land in
  the same stream the first time the player fights with the probe up.
- `nw_live.py --auto-capture`: starts the join probe whenever the game runs and no capture holds the
  lock, so the spawn full states are not missed. The server on 8769 runs with it now.
- Corrections from the player's eye: level = wire value + 1; riding = Mount state byte 1/5, not "mount
  id set" (state 4 = mount out, owner on foot, moving at walking speed over 4,995 samples).
- Trap: stopping the server while its watcher is on can leave a capture it started as an orphan
  (SIGINT is default in the child: `kill -INT <pid from /tmp/nw-capture.lock>` stops it cleanly).

## Update 2026-09-11 (21:10): the fight at 20:45

- Per-hit damage read from `OnDamage` (3601) and `OnDamageDealt` (2071): 34 hits summed to 9,811 on
  9,659 max health, the fraction field reproduces every amount; damage type byte = `IntID` of
  `javelindata_damagetypes` (player: Thrust + Nature; taken: Corruption, Lightning). Feed shows exact
  amounts, "you hit Grunt": the target u64 is bound to an entity by the equal health delta.
- Attributes were misread (a count that is not there); now five (points, id) pairs: 5, 5, 225, 5, 5 on
  ids 4..0. Id 2 = INT by datasheet order; the player has a projectile Thrust weapon (musket fits
  DEX/INT). Ask the player which attribute holds 225 to fix the order for good.
- Poses: owner mount `0x14 -> 0x17 -> 0x0f`, L3 `0x0c` hit / `0x0d` dying, L1 `0x23` likely weapon swap
  (paperdoll member-4 delta in the same frame), L1 `0x2b` (20:45:39, 1 s) unnamed.
- e1 named from a chat line sent by the self uuid (`PlayerManagerSelfIdentificationMsg` 1628).
- Ids: an entity's u64 network id is not in any of its own state chunks; it appears in
  `SpellComponentReplicatedState` (2912: caster, target, caster, 1.0) and `ProjectileReplicatedState`
  (16: position, velocity, projectile def u64, owner u64). Mapping u64 -> V1 needs the entity-create
  header, which the join probe does not hook.
- Server start trap: `pkill` + start in the same shell command left the new server dead twice; start
  it in its own command.
