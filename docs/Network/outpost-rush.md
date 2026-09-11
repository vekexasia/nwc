# Outpost Rush: one full match on the wire (2026-09-11, 21:51-22:19)

Capture: `Tools/nw_capture/logs/20260911-213342_live.log` (241 MB JSON lines, probe with 512-byte RMI
bodies) and the raw ledger `~/Downloads/opr_ledger.bin` (79 MB, 215,572 datagrams 21:33:42-22:21:32,
no gap over 5 s, sha256 `addc5b7f...`). The arena sits inside the main level (`NewWorld_VitaeEterna`)
around x 1150-1400, y 10850-11250; the player entered at 21:51:13 (`OnTeleportWithLoadingScreen`).

## Ground truth from the end screen

- Result: team 0 (the player's, blue) 1001, team 1 593. Victory.
- Team points: team 0 Luna 307, Sol 403, Astra 184, kills 107; team 1 Luna 141, Sol 91, Astra 284, kills 82.
- PetaWatt: score 1,320, 0 player kills, 0 NPC kills, 12 deaths, 2 NPC kill assists, 8 player kill
  assists, 2 NPC takedowns, 8 player takedowns, 1,167 objective points, 0 revives, 0 infused
  wood/ore/hide, damage 87,390, healing 0.
- Rankings (score, K/D/A, damage, healing, third column): async93 16,024 12/2/55 1,170,768 0 0;
  Gaelron-NWA 13,356 1/7/38 362,968 747,441 0; Bohemond 12,750 20/2/37 1,267,515 4,386 22,340;
  Vaanaa 12,538 0/2/21 25,624 1,140,857 6,193; Forged Carbon 12,340 22/5/34 1,373,533 25,183 0;
  Remedy 12,170 1/2/32 36,754 1,071,985 0; ToTor4 12,078 4/15/20 984,219 0 81,386; P3RS3R 10,773
  2/5/37 195,690 668,820 0.
- XP reward at 22:19:15: +10,000 (5,000 of it from the rested pool), `ProgressionComponent` 899.

## Read

- **Teams**: `WarboardComponentClientFacet_OnUpdateFullWarboardManifest` (3530): u16 version, then per
  team u16 count, count x (`05` + uuid), count x u8 index, u16 0. Sent at 21:51:13 (4 + 3 players),
  21:51:18 (7 + 5), 21:51:25 (9 + 5) and on later joins. `parse_warboard_manifest` in `decode_rmi.py`.
- **Who is who**: `PlayerComponentReplicatedState` (3935) of every player entity carries
  `05 <uuid 16> <len> <name> 05 <uuid 16>`; 68 entities matched, 60 agreeing with the hook's name (the
  rest were reused indices). `player_uuid_name` in `decode_rmi.py`. The live page colours allies and
  enemies from these two.
- **Deaths**: 12 `ClientSyncDeathRecap` (4299), all by players: name + `24` + uuid string + zeros + f32
  last hit + f32 max health (9,237). Matches the 12 deaths on the end screen.
- **Damage**: 292 `OnDamage` taken (sum 226,441 over 12 deaths) and 56 `OnDamageDealt` summing to
  94,714 against 87,390 on the end screen: the scoreboard column is not the plain sum of the entries
  (turret or NPC hits, or the absorbed part, are the likely difference).
- **Capture points**: `CapturePointReplicatedState` (333) on static entities at (1174, 11158),
  (1367, 10873), (1255, 10978), (1304, 11248) and a few more indices; full state 29 bytes
  (`01 03` + 16 zero bytes + `04`/`05` + zeros + `01 00`), deltas `01 02 <byte>` with the byte moving
  (01, 03, 28, 40, 4a, 53, 55, 62): not a team id, more like a progress or state counter. Which point
  is Luna, Sol or Astra is not known; the three names are not on the wire in these chunks.

## Read after the match: scoreboard, score, outposts (`decode_opr.py`, checked on the end screen)

The key was the varint. Both streams use the prefix varint with **little-endian continuation**: n
leading one bits in the first byte = n more bytes, the first byte keeps its low 7-n bits as the
lowest bits, each following byte adds 8 bits above (`8c 16` = 0x0c | 0x16 << 6 = 1,420; `c7 8f 05` =
7 | 0x8f << 5 | 0x05 << 13 = 45,543; `fa 21 00 38 03 10` = a 6-byte field mask). Read with a
big-endian tail (as `decode_alc_state.read_prefix_varint` does for 3+ bytes) the totals were garbage;
read this way every one lands on the end screen.

**`OnUpdateWarboardStats` (839)**, after the facet uuid: u16 version, u8 local player index, the local
row (mask + one varint per set bit), then two team blocks: u8 count, count x (u8 index, mask, values).
Values are running totals. Bits: 1 score, 2 damage, 7 deaths, 21 healing, 22 damage absorbed (the
third ranking column), 23 kills, 26 assists, 27 npc kill assists, 38 unread (0 all match). The first
message carries a full 9-field row for every player present (16 bytes each). Block 0 is the second
manifest list, block 1 the first (the player's team). 1,533 of 1,538 messages parse to the exact end
(the other five are cut at the probe's 512 bytes). All 40 players' final rows equal the end screen:
PetaWatt 1,320 / 87,390 / 12 deaths / 8 assists; async93 16,024 / 1,170,768 / 12 kills / 2 deaths /
55 assists; Gaelron-NWA 13,356, healing 747,441; Bohemond 12,750, 20 kills, healing 4,386, absorbed
22,340; Vaanaa, Forged Carbon, Remedy, ToTor4, P3RS3R, Gj.K. Skenderbot likewise.
`decode_opr.py --log <log>` prints the table; `--check` holds the bytes.

**`GameModeReplicatedState` (2343) on the mode entity (e13)**: the frequent delta `01 80 08 <count>
<u8> count x (key u32, 01, seq varint, value varint)` is a map keyed by u32; the same entries appear
inside larger deltas (`01 81 01 18 08 ff 4a6e9282 01 812e e93e1025`), found by key.
- `4a6e9282` = **team scores**, value = own team | other team << 16: 0x25103e9 = **1001 / 593**, the
  final score, at 22:19:15; 921 / 571 at 22:17 in the replay.
- `448dd922` = **Luna**, `ca02dec1` = **Sol**, `06a8de5f` = **Astra**: value bytes (owner team or ff,
  capturing team or ff, capture progress). Names by attribution: score ticks credited to each key
  while owned came out 339 / 459 / 199 for the player's team against 307 / 403 / 184 on the end
  screen (kill points spread in), 143 / 106 / 334 against 141 / 91 / 284 for the other team; the
  order is unambiguous. Team score = outposts + kills: 307 + 403 + 184 + 107 = 1001 exactly.
- Other keys in the map: e78c48f6 (1 once), 089f87c8, 10f630c5, 6c97151e (64-bit values, unread).
  The 257-byte `01 c0 00` snapshots hold the same keys with 8-byte values.

The Ghidra side (subagent report in private/decoder-state/opr/REPORT.md): `GameModeReplicatedState`
constructor `0x14329b160` registers gameModeId, gameModeMapId, participantFacetRefs,
participantStatuses, participantTeamIndexes, participantCharacterIds, raidIds, **syncedTimers**,
mapOrigin, mapSizeInTiles, tileUiFilenameIdAndRotation, tileVisited, linkedMode, globalAfflictionData
and ten Event slots (registration helper `FUN_141775c60`); which registered property the keyed map is
(syncedTimers is the natural candidate) is not proven. The `Warboard` strings in the binary
(`WarboardStatsEntry`, `WarboardStatData`, `ReusableScoreboard*`, `0x1482b2c90..0x1482b3840`) are
the AZ reflection of the client scoreboard; the RMI unmarshal was not located.

## Not read yet

- `CapturePointReplicatedState` (333) on the static outpost entities: which entity is Luna, Sol or
  Astra (the map above has no position); the 3-byte delta byte.
- The other map keys, the GameMode member bit order, `GroupData` (3451), `RaidData` (28), `Ownership`
  (3217), `Turret` (4276), `BeamAttack` (2947), `LootDrop` (2027), `DetectionVolumeEvent` (366).

## Message inventory during the match (rmi_samples from 21:51:13)

| type | count | name |
|---|---|---|
| 3451 | 56419 | GroupDataComponentReplicatedState |
| 2343 | 11228 | GameModeReplicatedState |
| 333 | 6928 | CapturePointReplicatedState |
| 3217 | 4922 | OwnershipComponentReplicatedState |
| 366 | 3268 | DetectionVolumeEventReplicatedState |
| 839 | 1538 | WarboardComponentClientFacet_OnUpdateWarboardStats |
| 5762 / 5946 | 1454 each | ItemVersionData / JsonItemData (inventory) |
| 3857 | 1287 | ObjectivesComponentReplicatedState |
| 2443 | 357 | LookTargetingComponentReplicatedState |
| 3601 | 292 | VitalsComponentClientFacet_OnDamage |
| 2027 | 270 | LootDropReplicatedState |
| 28 | 187 | RaidDataComponentReplicatedState |
| 293 / 4118 | 150 / 26 | chat |
| 2570 | 116 | OnServerSpreadshotProcessed (blunderbuss pellets) |
| 2071 | 56 | OnDamageDealt |
| 2968 / 3530 | 34 / 3+ | warboard manifest, incremental and full |
| 4299 | 12 | ClientSyncDeathRecap |
| 4276 | 14 | TurretReplicatedState |

State types listed here reach `rmi_samples` because the probe's `STATE_TYPES` set does not know them;
they carry no entity index there, the same chunks with the index are in `join_samples`.
