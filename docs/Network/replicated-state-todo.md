# Replicated states: decode TODO

What is left to decode after `ALCReplicatedState`, ordered by what our objective needs. Scope is the
channel-1 `ReplicatedStateBundle` members, not the channel-0 typed message catalog.

Context: a replicated state is one member of the `ReplicatedStateBundle` (message 8, channel 1) that
the server sends per entity. Every member starts with a registry `typeIndex` reference; one missing
or wrong codec makes the rest of the message garbage, so this is decoded one state at a time
([open-world-discord-decode-notes.md](open-world-discord-decode-notes.md):74-76).

## Census

130 replicated states are known by name, 117 of them seen in the community capture corpus and 13
never seen. Regenerate and verify:

```sh
.venv-capture/bin/python Tools/nw_capture/experimental/offline/list_replicated_states.py
.venv-capture/bin/python Tools/nw_capture/experimental/offline/list_replicated_states.py --missing
.venv-capture/bin/python Tools/nw_capture/experimental/offline/list_replicated_states.py --tsv > /tmp/states.tsv
.venv-capture/bin/python Tools/nw_capture/experimental/offline/list_replicated_states.py --check
```

Sources, both gitignored under `private/open-world-discord/attachments/`:

- `211_capture-triage.html`: the community catalog. Gives `type_idx` and name for the 130 states,
  plus a `seen` flag and an occurrence count per state in their corpus. The counting unit is not
  documented and we have not verified it; treat the counts as a presence signal only.
- `087_typeregistry.json`: 3487 entries with `typeIndex`, `index`, `uuid` and `Marshal`/`Unmarshal`
  addresses. All 130 typeIndexes are present here but **none of the entries carries a name**
  (`list_replicated_states.py --check` asserts this join), so the catalog is the only naming source.

The registry addresses apply to our build: typeIndex 11 `Unmarshal` is `NewWorld+0x2a327f0`, the
address our own static analysis names `FUN_142a327f0`
([alc-static-analysis.md](alc-static-analysis.md):50). Checked on ALC only - and see the trap in
"Traps" below before using that column.

## Status

| State | typeIndex | Status in this repo |
|---|---:|---|
| `ALCReplicatedState` | 11 | Decoded and verified: group-aware record payload, 1..9-byte mask reader, 48-property schema, `worldPosAbs`/`worldPosRel`, axis assignment cross-checked against 55739 community markers ([alc-protocol-reference.md](alc-protocol-reference.md), [decoder-state.md](decoder-state.md)) |
| `VitalsComponentReplicatedState` | 15 | **Health decoded from live payloads and validated** against the game's own numbers; the payload is one `[member mask][field mask][fields]` block per member in the state's order, so the remaining fields are mapped member by member ([decoder-state.md](decoder-state.md), [health-field.md](health-field.md)) |
| `PlayerComponentReplicatedState` | 3935 | Registry identity and one community reference body, no field map of our own. See below |
| everything else | - | Not started |

Open items on ALC itself, not new states: local-player identity and ownership, rotation/look
direction semantics, group-1 entries beyond bit 0, the quantised elevation mapping, and the
semantics of the ~14 unobserved fields ([decoder-state.md](decoder-state.md)).

### Vitals: what is decoded, and what the payload looks like

The payload is one `[member mask][field mask][fields]` block per member that changed, in the
state's member order, not one opcode per payload: the reader `0x17b4110` reads a member mask, then
that member's own field mask, consumes the fields of each set bit, then moves to the next member of
the state's descriptor vector. So the leading byte of an observed payload is member 0's member mask.
**Member 0 (`+0x7c0`, `HealthAmount`), field bit 0, is a big-endian float32**, and the
decoded deltas match what the game prints on screen (a `+57` heal, a `362` drain, a right-mouse drain
falling in 260.8 steps). Read it with
`Tools/nw_capture/experimental/offline/decode_vitals.py --log <log> [--object <addr>]` (self-check:
`--check`).

```text
01 01 46 1b 88 f3      member 0, field bit 0: health 9954.2
01 09 46 17 75 cb 03   member 0, field bits 0 and 3: health + one 1-byte field
08 02 ...              member 0 with field mask 08, then further members (not mapped)
02 01 ...              member 0 with field mask 02 (bit 0 clear: not the health field)
```

The member order is the order of the registration calls in the object builder `FUN_14671E040`:

| # | offset | member |
|---|---|---|
| 0 | `+0x7c0` | amount structure, `HealthAmount` |
| 1 | `+0x7e8` | amount structure (`StaminaAmount` in [health-field.md](health-field.md)) |
| 2 | `+0x810` | amount structure (`ManaAmount` in [health-field.md](health-field.md)) |
| 3 | `+0x970` | `replicatedAfflictionsHotData` |
| 4 | `+0xc18` | `replicatedAfflictionsColdData` |
| 5 | `+0xec0` | `vitalsData` |
| 6 | `+0x928` | `healthChangeFlags` |
| 7-12 | `+0x838`..`+0x900` | six unnamed `0x28`-byte structures |
| 13-18 | `+0xf48`..`+0x1000` | `vitalsId`, `vitalsCategoryId`, `vitalsLevel`, `invulnerability`, `displayImmuneWhenInvulnerable`, `maxHealth` |

Member 1, field bit 0, is a float32 in `[0, 100]` (64.10 right before the drain, refilled to 100.0
within two seconds): mana is the obvious reading, but not proven.

Still open: the bits and widths of the other members, stamina in particular (a capture with the
sprint phase showed no resource falling while sprinting and no member-1 update from the spells, and
the character was standing in a settlement, where spells cannot be cast - injected keyboard input
itself is verified working, see [NEXT_SESSION.md](../NEXT_SESSION.md)), how the non-health amounts
encode their value, and the reader's third stage (a delta list, varint plus member vtable `+0x50`).

### PlayerComponentReplicatedState: what we have

Registry identity, from `087_typeregistry.json` and confirmed against the local `NewWorld.exe`: typeIndex
3935, registry index 3160, uuid `BDDDA784-A6E7-416B-A041-449920D90FB6` (present in the executable in
lowercase, file offset `0x8526590`), `Unmarshal` `NewWorld+0x6573d60` (in `.text`, same prologue as the
ALC `Unmarshal`), `CreateInstance` `NewWorld+0x6573b80`, `Marshal` `NewWorld+0x7f8b00`.

In the executable the name appears twice and both are weak anchors: the plain literal
`PlayerComponentReplicatedState` at VA `0x14a1d5160` and the mangled symbol
`?InstallRegistrationHook@VPlayerComponentReplicatedState@MB@@@Hub@Amazon@@YA_NXZ` at `0x14a24994d`,
both inside a `.data` blob of mangled symbol names, with **no pointer referencing either**. The ALC
method does not transfer: ALC has one static record whose `-0xA8` is the name pointer, and its
property names sit next to the name in `.rdata`; for PlayerComponent there is no such record, and the
community field names (`character_name`, `player_type`, `platform_account_id`, ...) are not strings in
this executable at all (checked; only the unrelated `home_world_id` exists). So there is no ordered
property list to read off the image, unlike ALC's 48.

Reference body: `private/open-world-discord/attachments/105_message.txt` is someone else's decoded
spawn bundle (`type_idx` 8) with a full `PlayerComponentReplicatedState` (create, 29 fields) plus
`ALCReplicatedState` (create) and the real spawn position. Their field names and values are their
tooling's output for their build, not our decode, and the file carries a real SteamID64: keep it
private, do not quote the values in tracked docs.

Discord, on this state: it is the spawn `create` member and carries the character/world ids
(`ask-a-question.md:635`); the entity/replica id that links it to `ClientAddEntryMsg(164)` is in the
bundle header, **not** inside PlayerComponent; sending it alone fails to parse the bundle
(`ask-a-question.md:550`); the local-ownership/primary flag is separate and was still unresolved there.

## How a state is read now (the working loop)

1. **Probe**: hook the client-side reader of the state, not the registry handler. Record, per call,
   the object pointer, the bytes consumed and the payload (`nw_state_probe.js` does this for the
   Vitals path, with the `worldPosAbs` reader as a control; `decode_alc_state.py` covers ALC from a
   ledger).
2. **Capture**: `nw_capture_probe.py --probe <abs path> --seconds N`. Captures need **no focus and no
   input**; a five second capture already gives hundreds of state reads over dozens of entities.
   Injecting input is the only part that needs the focused window (`nw_vmouse.py --focus --restore`),
   and `capture_lock.py` makes sure two captures never overlap.
3. **Decode**: `decode_vitals.py` / `decode_alc_state.py` turn a log into values.
4. **Validate by behaviour, not by plausibility**: drive one action and check the value against the
   game's own output (the on-screen damage numbers for health, the jump arc for `distGround`, the
   dodge for `segmentedStamina`). A float that merely looks plausible is not evidence.

`nw_actions.py` plays a timed sequence (sprint, stand, casts, right-mouse self-drain) and writes a
timeline, so a capture can be read per phase; that is how the player's own Vitals object is
identified (the object whose health falls during the drain is the local player).

## Traps that cost real time

- The registry `Unmarshal` column is **not** what the client calls to read a state: hooking those
  addresses fires zero times while the state is clearly being decoded. Hook the reader path itself.
- Addresses from Ghidra listings are **absolute**; a probe wants **RVAs** (`absolute - 0x140000000`).
  Passing an absolute address as an RVA gives an access violation and kills the whole hook install.
- Do not locate records by matching short byte windows: two attempts locked onto a periodic 166-byte
  heartbeat with an incrementing counter and produced plausible nonsense. Prefer a reader whose
  cursor delta gives the length directly.

## TODO, in order

Tier 1 - self and rendering. Closes the "which record is me" gap and what the player looks like.

| State | typeIndex | Why |
|---|---:|---|
| `PlayerComponentReplicatedState` | 3935 | the create member carrying character/world ids; the identity gap the trail currently fills with a monotonicity heuristic |
| `GdeMetadataReplicatedState` | 10 | required for the character to appear ([notes](open-world-discord-decode-notes.md):76) |
| `PlayerAppearanceComponentReplicatedState` | 1195 | appearance |
| `PaperdollComponentReplicatedState` | 3183 | equipment; community notes on its `descriptor_mask` groups exist |

Tier 2 - player numbers, for a marker readout.

| State | typeIndex | Why |
|---|---:|---|
| `VitalsComponentReplicatedState` | 15 | Health done (member 0, bit 0); the member order is known, so the work left is the bits and widths of members 1..18 and the delta stage |
| `AttributeComponentReplicatedState` | 129 | attributes |
| `StatMultiplierTableComponentReplicatedState` | 1525 | stat multipliers |

Tier 3 - other entities on the map. Players carry their position in ALC; these are for everything
else.

| State | typeIndex | Why |
|---|---:|---|
| `PositionInTheWorldReplicatedState` | 13 | position of non-player entities; the historical catalog names it too ([live-position-map-feasibility.md](live-position-map-feasibility.md)) |
| `PlayerNameTagComponentReplicatedState` | 100 | who a marker belongs to |
| `GroupDataComponentReplicatedState` | 3451 | group members |
| `MountComponentReplicatedState` | 5620 | mount state |

Tier 4 - the remaining 120 states, on demand. Do not decode them for coverage.

Never seen in the community corpus, so there is no reference body to check a reader against:
`Grit` (17), `TestFacetedComponent` (41), `TwitchStream` (610),
`FtueDetectionVolumeTeleport` (1055), `GroupFinderGroupDataComponent` (1091), `Arena` (1296),
`AggregateContractCountComponent` (1742), `ExampleFacetedComponent` (2092), `ReplicatedState`
(2164), `NotificationServiceComponent` (3340), `TestTransactorComponent` (4263),
`ClientPathingComponent` (5915), `TransformLinkComponent` (5980).

## Infrastructure, not a state

- **Record-length oracle.** The record layer has no length field, so walking a body past a record of
  an unknown type needs its payload length. With the length of every type, old captures (and the
  community corpus) become decodable offline, with no game, no probe and no focus. The reader-hook
  route that worked for Vitals gives exact lengths, so this is reachable one state at a time;
  `record_lengths.py` exists but its window matching is unreliable.
- **Live reader.** The probe appends to its log every 500 ms, so a tailing decoder can print the
  player's position and health as they change, and feed `nw_map_trail.js` for a moving trail.

## Recipe for one state

The path already walked for ALC, reuse it instead of re-deriving ([alc-static-analysis.md](alc-static-analysis.md),
[ghidra-workflow.md](ghidra-workflow.md)):

1. `typeIndex` -> registry `Unmarshal` address (`list_replicated_states.py --tsv` gives it). That is
   the Ghidra entry point; no hunting by string.
2. Factory -> schema builder -> the ordered property-name list and the per-property readers, as done
   for the ALC 48.
3. Reader -> wire width and field order; check the consumed widths against a real body.
4. Confirm the whole member consumes exactly, inside the bundle, before naming anything as a value.

Then hook the client-side reader (see "How a state is read now") and validate each field by driving
an action, because the property table alone does not say which member and which mask bit carry a field.

Before decoding a state, check the capture actually contains it: our Test teleport ledger resolves
only type reference 11, so a new state needs a capture where its `typeIndex` is present
([offline-framing-findings.md](offline-framing-findings.md):382,
`decode_wire_type_ids.py` for a live trace).

## Out of scope

- The 13 never-seen states have no reference body; skip until one appears in a capture.
- Do not present a decoded field as a coordinate, a self-identity or a trail without the checks in
  [live-position-map-feasibility.md](live-position-map-feasibility.md).
- Not the channel-0 typed message catalog (3487 entries); that is a separate list. It does hold the
  damage/heal event messages (`VitalsComponentClientFacet_OnDamage` is `type_idx` 3601,
  `DamageReceiverComponentClientFacet_OnDamageDealt` is 2071), so if a combat log is ever wanted,
  that is where to start.
