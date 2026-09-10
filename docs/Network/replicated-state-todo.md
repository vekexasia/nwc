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
([alc-static-analysis.md](alc-static-analysis.md):50). Checked on ALC only.

## Status

| State | typeIndex | Status in this repo |
|---|---:|---|
| `ALCReplicatedState` | 11 | Decoded and verified: group-aware record payload, 1..9-byte mask reader, 48-property schema, `worldPosAbs`/`worldPosRel`, axis assignment cross-checked against 55739 community markers ([alc-protocol-reference.md](alc-protocol-reference.md), [decoder-state.md](decoder-state.md)) |
| `VitalsComponentReplicatedState` | 15 | Static 19-field table recovered, including codec readers and scalar widths; no type-15 payload in our capture yet ([health-field.md](health-field.md)) |
| `PlayerComponentReplicatedState` | 3935 | Registry identity and one community reference body, no field map of our own. See below |
| everything else | - | Not started |

Open items on ALC itself, not new states: local-player identity and ownership, rotation/look
direction semantics, group-1 entries beyond bit 0, the quantised elevation mapping, and the
semantics of the ~14 unobserved fields ([decoder-state.md](decoder-state.md)).

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
| `VitalsComponentReplicatedState` | 15 | Static HP/max/rate codec map recovered; live type-15 payload and semantics remain open ([health-field.md](health-field.md)) |
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

## Recipe for one state

The path already walked for ALC, reuse it instead of re-deriving ([alc-static-analysis.md](alc-static-analysis.md),
[ghidra-workflow.md](ghidra-workflow.md)):

1. `typeIndex` -> registry `Unmarshal` address (`list_replicated_states.py --tsv` gives it). That is
   the Ghidra entry point; no hunting by string.
2. Factory -> schema builder -> the ordered property-name list and the per-property readers, as done
   for the ALC 48.
3. Reader -> wire width and field order; check the consumed widths against a real body.
4. Confirm the whole member consumes exactly, inside the bundle, before naming anything as a value.

Before decoding a state, check the capture actually contains it: our Test teleport ledger resolves
only type reference 11, so a new state needs a capture where its `typeIndex` is present
([offline-framing-findings.md](offline-framing-findings.md):382,
`decode_wire_type_ids.py` for a live trace).

## Out of scope

- The 13 never-seen states have no reference body; skip until one appears in a capture.
- Do not present a decoded field as a coordinate, a self-identity or a trail without the checks in
  [live-position-map-feasibility.md](live-position-map-feasibility.md).
- Not the channel-0 typed message catalog (3487 entries); that is a separate list.
