# Outpost Rush on the wire

How a New World client learns the scoreboard, the team score and the state of the three outposts
during an Outpost Rush match, read from one decrypted DTLS session (2026-09-11, 21:51-22:19, won
1001-593) and checked field by field against the end-of-match screen. Everything below is verified on
those bytes unless marked *inferred*.

Companion code: `Tools/nw_capture/experimental/offline/decode_opr.py` (`--check` replays the worked
examples, `--log <log>` prints the final scoreboard of a capture) and `decode_rmi.py` (manifest,
identity, chat, damage, death recap). Live view: `nw_live.py` (Outpost Rush card, team colours,
replay mode).

## 1. Transport in one paragraph

The client talks GridMate over DTLS. Inside a datagram, the carrier splits into channel 0 (typed
messages: RMIs and direct messages, each starting with a type index from the catalogue) and channel 1
(replicated state chunks: one per component, addressed by entity index V1 and component type index).
The join probe (`nw_join_probe.js`) hooks the component reader and the typed-message reader and logs
both as JSON lines (`join_samples` for state chunks with their entity index, `rmi_samples` for typed
messages with the first 512 bytes of body). Every RMI to a client facet begins with the 16-byte uuid
of the receiving facet; every facet of the local player's entity shares the same last 8 bytes.

## 2. The varint

The Outpost Rush streams use a prefix varint with little-endian continuation:

- count the leading one bits of the first byte: `n`;
- the value uses `n` more bytes;
- the first byte keeps its low `7-n` bits as the lowest bits of the value;
- each following byte adds 8 bits above, in order.

| bytes | n | value |
|---|---:|---|
| `2d` | 0 | 45 |
| `8c 16` | 1 | 0x0c + (0x16 << 6) = 1,420 |
| `c7 8f 05` | 2 | 7 + (0x8f << 5) + (0x05 << 13) = 45,543 |
| `e2 00 00 02` | 3 | 2 + (0x02 << 20) = 2,097,154; as a mask, bits {1, 21} |
| `fa 21 00 38 03 10` | 5 | bits {1, 2, 7, 21, 22, 23, 26, 27, 38} |

Field masks are encoded the same way, which is why a mask with high bits set arrives as a 4- or 6-byte
varint. Reading the tail big-endian (as the ALC position reader does for 3+ bytes) produces garbage
here; the totals only landed on the end screen with this reading.

## 3. Rosters: who is on which team

### 3.1 `WarboardComponentClientFacet_OnUpdateFullWarboardManifest` (type 3530)

After the facet uuid:

```
u16 version
per team (two teams):
    u16 count
    count x ( 05, uuid[16] )        character uuids
    count x u8                      warboard index of each uuid, same order
    u16 0
```

Sent at the start (4 + 3 players at 21:51:13, 7 + 5 five seconds later, 9 + 5 at 21:51:25) and on
later joins. The first list is the local player's team.

### 3.2 `OnUpdateWarboardManifest` (type 2968), incremental

```
u16 version
per team:
    u16 added
    added x ( 05, uuid[16] ), added x u8 index
    u16 removed                     (no removal observed; shape after it unread)
```

Example `0008 0000 0000 0001 05 <uuid> 03 0000`: nothing for team 0, one player added to team 1 at
index 3.

### 3.3 uuid to name to entity: `PlayerComponentReplicatedState` (type 3935)

The player component state of every player entity in scope contains

```
05, uuid[16], u8 len, name[len], 05, uuid[16] ...
```

68 player entities carried it in the match log, 60 agreeing with the name the hook read from the
object (the other 8 were reused entity indices). This is the join between the roster and the dots on
the map, and it names the local player too.

## 4. The scoreboard stream: `OnUpdateWarboardStats` (type 839)

After the facet uuid:

```
u16 version
u8  local index                     the local player's warboard index (3 in the match)
row local                           the local player's own totals
block                               team block A
block                               team block B

row   = mask varint, then one varint per set bit of mask, ascending bit order
block = u8 count, count x ( u8 index, row )
```

Values are **running totals**, not deltas. Block A is the *second* manifest list, block B the first
(the local team). A row carries only the stats that changed since the last message; the first
message of the match carries a full nine-field row for every player present (16 bytes each: index,
6-byte mask, nine one-byte zeros).

### 4.1 Stat bits

| bit | stat | end-screen column |
|---:|---|---|
| 1 | score | Score |
| 2 | damage dealt | Damage |
| 7 | deaths | D of K/D/A |
| 21 | healing done | Healing |
| 22 | damage absorbed | third numeric column of the rankings |
| 23 | player kills | K of K/D/A |
| 26 | player kill assists | A of K/D/A |
| 27 | NPC kill assists | Performance tab, "NPC Kill Assists" |
| 38 | unknown | 0 for every player all match |

Objective points, revives and infused resources are not in this stream.

### 4.2 Worked example

The local player's ninth death, 22:13:33, body after the uuid:

```
0028 03 8602 aa0d d05e0a 09  03 0e 06 837e d5085f  0d 06 8477 c12a68  0f 02 a569  03 13 06 9c46 c1353a  12 02 a955  03 8602 aa0d d05e0a 09
^    ^  ^    ^    ^      ^   ^  block A: 3 rows                                            block B: 3 rows
|    |  |    |    |      |   count
|    |  |    |    |      deaths 9
|    |  |    |    damage 84,944
|    |  |    score 874
|    |  mask 0x86 = bits {1, 2, 7}
|    local index 3
version 0x28
```

Block A: index 14 (mask 06: score 8,067, damage 778,517), index 13 (score 7,620, damage 853,313),
index 15 (mask 02: score 6,757). Block B: index 19 (score 4,508, damage 476,833), index 18 (score
5,481) and index 3, the local player again with the same three values.

### 4.3 Verification

1,533 of the 1,538 messages of the match parse to their exact last byte (the other five were cut by
the probe's 512-byte cap). Taking the last value seen per (block, index, bit):

| player | wire | end screen |
|---|---|---|
| PetaWatt | 1,320 score, 0 kills, 12 deaths, 8 assists, 87,390 damage, 2 NPC assists | 1,320 · 0/12/8 · 87,390 · 2 |
| async93 | 16,024 · 12/2/55 · 1,170,768 · healing 0 | 16,024 · 12/2/55 · 1,170,768 · 0 |
| Gaelron-NWA | 13,356 · 1/7/38 · 362,968 · healing 747,441 | same |
| Bohemond | 12,750 · 20/2/37 · 1,267,515 · healing 4,386 · absorbed 22,340 | same |
| Vaanaa | 12,538 · 0/2/21 · 25,624 · healing 1,140,857 · absorbed 6,193 | same |
| Forged Carbon | 12,340 · 22/5/34 · 1,373,533 · healing 25,183 | same |
| Remedy | 12,170 · 1/2/32 · 36,754 · healing 1,071,985 | same |
| ToTor4 | 12,078 · 4/15/20 · 984,219 · absorbed 81,386 | same |
| P3RS3R | 10,773 · 2/5/37 · 195,690 · healing 668,820 | same |

All 40 rows reproduce the rankings tab.

## 5. Score and outposts: `GameModeReplicatedState` (type 2343)

One entity carries the game mode (V1 = 13 in the match). Its most frequent delta is

```
01 80 08          member mask 0x200 (bit 9), one member
u8 count, u8
count x ( key u32, 01, seq varint, value varint )
```

a map keyed by u32. The same entries appear inside larger deltas together with other members
(`01 81 01 18 08 ff 4a6e9282 01 812e e93e1025 ...`) and, with 8-byte values, in the 257-byte
snapshots (`01 c0 00 ...`); the decoder finds them by key.

| key | meaning | value |
|---|---|---|
| `4a6e9282` | team scores | own team + (other team << 16). `e9 3e 10 25` = 0x25103e9 = **1001 / 593**, the final score, at 22:19:15 |
| `448dd922` | outpost **Luna** | byte 0 owner team (`ff` none), byte 1 capturing team (`ff` none), byte 2 capture progress |
| `ca02dec1` | outpost **Sol** | same |
| `06a8de5f` | outpost **Astra** | same |
| `e78c48f6` | set to 1 once at 21:52:46 (match start?) | |
| `089f87c8`, `10f630c5`, `6c97151e` | unread, 64-bit values | |

Team score = outposts + kills: 307 + 403 + 184 + 107 = 1001 for the winning team.

*Inferred*: the outpost names. Each score tick was credited to the outposts the scoring team owned at
that moment; the totals came out 339 / 459 / 199 for the local team against 307 / 403 / 184 on the end
screen (kill points are spread in) and 143 / 106 / 334 against 141 / 91 / 284 for the other, the
same order on both sides. The Ghidra property list of the type (`gameModeId`, `gameModeMapId`,
`participantFacetRefs`, `participantStatuses`, `participantTeamIndexes`, `participantCharacterIds`,
`raidIds`, `syncedTimers`, `mapOrigin`, `mapSizeInTiles`, `tileUiFilenameIdAndRotation`,
`tileVisited`, `linkedMode`, `globalAfflictionData`, ten event slots) does not say which registered
property this map is; `syncedTimers` is the natural candidate.

## 6. Outposts on the ground: `CapturePointReplicatedState` (type 333)

Static entities (position from `PositionInTheWorldReplicatedState`, type 13). Full state 29 bytes
(`01 03`, 16 zero bytes, a byte 04 or 05, zeros, `01 00`); the frequent 3-byte delta `01 02 xx` is
member 1 = **capture progress 0..100** (on the Luna entity it tracked the map's progress byte: 86 with
84..87, 96 with 96..99).

*Inferred*: the arena's capture-point entities cluster at (1272, 11018), (1370, 10880) and
(1174, 11158) in world coordinates (the arena lives inside the main level, `NewWorld_VitaeEterna`,
around x 1150-1400, y 10850-11250). The middle cluster is Sol (the midpoint of the other two), Luna is
the one nearer the spawn of the team that held Luna 307 to 141 (that team spawned at (1230, 10751)),
Astra the far one. Other 333 entities (gates, spawns) are not named yet.

## 7. Combat messages that matter in a match

| type | message | body after the facet uuid |
|---:|---|---|
| 3601 | `VitalsComponentClientFacet_OnDamage` (hit taken) | receiver id u64, flags u16, damage / max health f32, hit position xyz f32, u8 count, count x (damage type u8, amount f32, f32) |
| 2071 | `DamageReceiverComponentClientFacet_OnDamageDealt` (hit landed) | source id u64 byte-reversed, target id u64, source id, attack instance id u64, flags u16 (bit 0x4000 critical, 0x8000 absorbed, 0x0002 damage-over-time tick), u8 count, entries as above |
| 4299 | `VitalsComponentClientFacet_ClientSyncDeathRecap` | u8 len, killer (a vitals name key for a mob, or the character name followed by `24` + 36-char uuid for a player), zero bytes, f32 last hit, f32 own max health |
| 2415 / 3916 | `AITargetableComponentClientFacet_OnSelectedAsTarget` / `OnUnSelectedAsTarget` | u64 id of the mob that starts / stops targeting the player |
| 4118 / 293 | chat, single and batched | uuid string, name, 6 bytes (channel), text, zeros, Steam id string |

The damage type byte is the `IntID` column of `javelindata_damagetypes.datasheet` (3 Standard,
5 Thrust, 8 Arcane, 9 Fire, 10 Lightning, 11 Corruption, 13 Ice, 14 Nature). In the match the 12
death recaps matched the 12 deaths on the board; the 56 dealt entries summed to 94,714 against 87,390
on the board, so the scoreboard's damage is filtered (turret or NPC hits, or the absorbed part).

## 8. Reproducing

```
# the scoreboard of a capture
.venv-capture/bin/python Tools/nw_capture/experimental/offline/decode_opr.py --log Tools/nw_capture/logs/<run>_live.log

# the worked examples
.venv-capture/bin/python Tools/nw_capture/experimental/offline/decode_opr.py --check
.venv-capture/bin/python Tools/nw_capture/experimental/offline/decode_rmi.py --check

# watch a finished log as it happened (page on :8770)
.venv-capture/bin/python Tools/nw_capture/experimental/nw_live.py --log Tools/nw_capture/logs/<run>_live.log \
    --port 8770 --replay --speed 4 --replay-from 21:51:00
```

The raw session is `opr_ledger.bin` (79 MB, 215,572 datagrams, 21:33:42-22:21:32, no gap over 5 s):
flat records `<u32 magic><u64 ts_ms><u8 dir><3 pad><u64 ssl_ptr><u32 len><payload>`, one plaintext
DTLS application record each, readable with `Tools/nw_capture/decode_dtls_ledger.py`. It contains the
character names and uuids of about 40 players and the Steam id of whoever typed in chat.

## 9. Open

- The member bit order of `GameModeReplicatedState` (which property the keyed map is).
- The three unread map keys and the 8-byte layout of the snapshot form.
- `GroupDataComponentReplicatedState` (3451, 56k chunks on 10 entities: raid groups),
  `RaidDataComponentReplicatedState` (28), `TurretReplicatedState` (4276),
  `BeamAttackComponentReplicatedState` (2947), `LootDropReplicatedState` (2027, the infused resources),
  `DetectionVolumeEventReplicatedState` (366).
- Which `CapturePointReplicatedState` entities are the gates; the scoreboard's damage filter.
- Whether the ALC reader's big-endian 3-byte varint is right for its own fields, now that a
  little-endian one is proven elsewhere.
