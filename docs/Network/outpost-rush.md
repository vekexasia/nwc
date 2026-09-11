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
- **Damage**: 292 `OnDamage` taken, 56 `OnDamageDealt` (the player landed few hits: 87,390 total on
  the end screen; the RMI entries sum is the check to run).
- **Capture points**: `CapturePointReplicatedState` (333) on static entities at (1174, 11158),
  (1367, 10873), (1255, 10978), (1304, 11248) and a few more indices; full state 29 bytes
  (`01 03` + 16 zero bytes + `04`/`05` + zeros + `01 00`), deltas `01 02 <byte>` with the byte moving
  (01, 03, 28, 40, 4a, 53, 55, 62): not a team id, more like a progress or state counter. Which point
  is Luna, Sol or Astra is not known; the three names are not on the wire in these chunks.

## Not read yet (this is what the dump is for)

- **Team score**: 1001 and 593 never appear together in one record in the last minutes as u16, u32,
  f32, LEB128 or prefix varint; the per-outpost points (307/403/184, 141/91/284) neither. The client
  most likely accumulates them from the compact streams below.
- **`GameModeReplicatedState` (2343) on entity 13**: 11,228 deltas. Shape `01 80 08 01 01 <id u32>
  01 <seq varint> <fields>` with three recurring ids `448dd922`, `ca02dec1`, `4a6e9282` (three
  outposts or two teams plus one), fields like `c0 08 <v>` with v climbing 16 -> 160 over seven
  seconds and `e0 22 50 16` counters. Prefix varints (`decode_alc_state.read_prefix_varint`).
- **`OnUpdateWarboardStats` (839)**: 1,538 messages, the per-player scoreboard deltas. Header `u16
  version, 03`, then a prefix varint (0 or `80 02`), then blocks of `u8 count` + rows; the first
  message (21:51:13) has 3 + 4 rows of 17 bytes (`idx` + `fa21 0038 0310` + zeros) for the 3 + 4
  players present, i.e. the initial stat vector; later rows are `idx` + compact varint pairs of
  variable length. Every one of the 12 deaths has a 839 message within 2 s. Neither "(stat, value)
  pairs until 0" nor "count + pairs" parses more than 8 of 1,538 messages to the exact end, so the row
  encoding is still open. The end-screen numbers above are the oracle: summing the right field per
  player index must give 12 deaths and 87,390 damage for PetaWatt (team 0, index 3 in the first
  manifest) and 16,024 score for async93.
- `GroupDataComponentReplicatedState` (3451, 56,419 chunks), `RaidDataComponentReplicatedState` (28),
  `OwnershipComponentReplicatedState` (3217: owner uuid string + owner name, for turrets and siege),
  `TurretReplicatedState` (4276), `BeamAttackComponentReplicatedState` (2947), `LootDropReplicatedState`
  (2027: the infused resources), `DetectionVolumeEventReplicatedState` (366).

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
