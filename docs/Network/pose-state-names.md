# Mapping `slayerStateId` to pose names

**Status: final checkpoint, 2026-09-11.** The wire ids are verified, but the id-to-asset-name table was not recovered.

Do not treat the semantic labels below as a complete server vocabulary.
## Result at a glance

| Route | Result |
|---|---|
| A: client binary/static analysis | Found the ALC/slayer schema, runtime component names, and code/data addresses. The executable contains the slayer and action-system vocabulary, but no direct `slayerStateId -> name` table has been found. The useful action strings have no ordinary Ghidra code xrefs. |
| B: installed pak/assets | Found and extracted the player CAGE grid and 53 `playeractions_*.actionlist` files from `SharedDataStrm-part7.pak` (plus the dagger list from `SharedDataStrm-part6.pak`). Found the player Mannequin ADB family in `SharedDataStrm.pak` and extracted `player.adb` plus its XML definitions. The XML contains fragment names and animation names, but no numeric network state ids. |

## Route A: `NewWorld.exe`

Analysis target: `NewWorld.exe`, image base `0x140000000`, Ghidra project
`~/ghidra-projects/nw`; static analysis was performed without auto-analysis.

### Addresses and findings

* `0x142a3b050` is the `ALCReplicatedState` type factory. It allocates the
  `0x1560`-byte object and calls the schema builder at `0x142a35db0`.
* `0x1480fed90` is the type name `ALCReplicatedState`; `0x1480ffa68` is
  `ALCReplicatedStateAllocator`.
* The schema name strings are in the range `0x1480ffa84..0x1480ffe30`.
  In particular: `slayerSeqTimeRel` at `0x1480ffaa0`, `slayerSeqTimeAbs`
  at `0x1480ffab8`, `slayerStateId` at `0x1480ffaf8`,
  `slayerStateIdStarted` at `0x1480ffb08`, `slayerSequenceId` at
  `0x1480ffb20`, `slayerScriptLayers` at `0x1480ffd70`, and
  `slayerScriptFlags` at `0x1480ffd88`.
* The four state/sequence layers are registered at state offsets:
  `slayerStateId` `+0xac0`, `+0xae8`, `+0xb10`, `+0xb38`;
  `slayerStateIdStarted` `+0xb60`, `+0xb80`, `+0xba0`, `+0xbc0`;
  `slayerSequenceId` `+0xbe0`, `+0xc08`, `+0xc30`, `+0xc58`.
  Their corresponding time pairs are at `+0xc88/+0xcb0`,
  `+0xce0/+0xd08`, `+0xd38/+0xd60`, and `+0xd90/+0xdb8`.
* The state-id and sequence-id reader is `0x142a42e60`, a prefix-varint
  reader consuming 1..5 bytes. `slayerStateIdStarted` uses the two-byte
  reader at `0x142a42e10`; sequence absolute time uses the half-float reader
  at `0x142a42f80`; relative time uses the one-byte quantised reader at
  `0x142a42eb0`.
* The relevant runtime/static component strings are present at:
  `ActionListComponentSlayerScript` `0x148390930`,
  `m_actionGridNew` `0x148388278`, `m_animationDatabase` `0x148388298`,
  `m_scopeData` `0x1483882b0`, `m_spawnAction` `0x1483882c0`,
  `m_useSlayerScript` `0x1483882d0`, and `m_slayerScriptName`
  `0x1483882e8`. The RIP-relative loads for these were found in the
  `0x144845ee5..0x144846380` region. `SlayerScriptEventSetAISequence` is
  at string `0x148387ab0`; `SlayerScriptEventSetAIMannequinTagState` is at
  `0x148387b30`.
* User-facing/action vocabulary is visible around `0x1480782c8` onward:
  `Nav`, `Nav_Start`, `Sprint`, `Sprint_Start`, and `Dodge` (the latter at
  `0x1480782f8`). A raw RIP-relative scan found no load of those action-name
  strings in the executable's code. This means the missing lookup is likely
  keyed by an asset/hash/table representation rather than a direct string
  reference.
* Other useful slayer strings include `slayerScriptDataMap` at `0x1482195aa`,
  `slayer-script` at `0x1482348fe`, `slayer_script` at `0x14827b6b3`,
  `slayerScriptName` at `0x1483882ea`, and
  `ActionListComponentSlayerScript` references at `0x1448a6261` and
  `0x1448a63c4`.

### Wire observations that constrain the lookup

The live traces already identify examples in layer 0: `0x1f` idle, `0x1a`
walk, `0x0d` walk-to-run, `0x0b` dodge, `0x07` sprint, `0x0c` landing,
`0x1b` stopping, `0x0e` jump, `0x09` gathering, and `0x08`/`0x0a` ability or
attack values in one observed weapon configuration. Layer 1 includes `0x2c`
weapon draw, `0x2d` ready, `0x21` light attack, `0x27` heavy attack,
`0x24` weapon ability, and `0x25` block. These are observed labels, not a
static name table. Weapon layers are script-dependent.

## Route B: installed pak and asset extraction

The installed game contains ZIP-compatible paks with Oodle-compressed entries.
The local Oodle library used for the checkpoint was `/tmp/liboo2corelinux64.so.9`.
The exploratory extractor was `/tmp/oodle_extract.py`; its outputs are temporary
and are not repository data.

### CAGE/action assets extracted

Source: `assets/SharedDataStrm-part7.pak`.

* `sharedassets/springboardentitites/playerdata/cage/player.grid` extracted
  exactly: compressed 11,745 bytes, raw 120,137 bytes.
* 47 `playeractions_*.actionlist` files extracted exactly with Oodle method
  15. The set includes `playeractions_idle`, `nav`, `sprint`,
  `sprintposetransition`, `dodge`, `fall`, `traversal`, `gather`, `fishing`,
  `mount`, `swim`, `postureinput`, `attack`, `block`, `sheathe`, `use`,
  `global`, and the weapon ability lists for blunderbuss, bow, firemagic,
  flail, greataxe, greatsword, hatchet, icemagic, lifemagic, musket, rapier,
  runes, spear, sword, voidgauntlet, and warhammer.
* The extracted files are plain XML. `player.grid` defines aliases such as
  `Idle`, `Nav`, `Fall`, `Sprint`, `Land`, `Dodge`, `Reaction`, `Sheathe`,
  `Jump`, `Block`, `Mount`, `Fishing`, and `Swim`. For example,
  `playeractions_sprint.actionlist` has `Action Name="Sprint_Start"`
  and `Action Name="Sprint"`, both with corresponding fragment names;
  `playeractions_idle.actionlist` has the `Idle` action and `Idle` fragment.
* This route establishes the script/fragment vocabulary and confirms that the
  observed behavior is driven by named CAGE actions. It does **not** expose
  the numeric ids in the extracted XML: searching the extracted CAGE files
  for `slayerStateId`, `stateId`, and numeric state-id declarations yielded
  no mapping.

### Mannequin/ADB assets found

Source: `assets/SharedDataStrm.pak` (entry listing from `/tmp/cage-list.txt`).
The player ADB family is under `animations/mannequin/adb/player/`:

* `player.adb` (extracted, 3,008,850 bytes),
  `playermaleactions.xml` (41,729 bytes),
  `playermalecontrollerdefs.xml` (79,692 bytes), and
  `playermaletags.xml` (5,941 bytes).
* Weapon sub-ADBs found and extracted: `player_1h_melee`,
  `player_1h_ranged`, `player_2h_melee`, `player_2h_ranged`, `player_axe`,
  `player_blunderbuss`, `player_bow`, `player_club`, `player_dagger`,
  `player_demohammer`, `player_fishingpole`, `player_flail`, `player_greataxe`,
  `player_greatsword`, `player_knife`, `player_magicgauntlet`,
  `player_magicgauntlet_ice`, `player_magicgauntlet_void`,
  `player_magicstaff`, `player_magicstaff_fire`, `player_magicstaff_heal`,
  `player_mount`, `player_offhand`, `player_pick`, `player_rapier`,
  `player_rifle`, `player_spear`, `player_sword`, and `player_warhammer`.
* `player.adb` declares `FragDef=".../PlayerMaleActions.xml"` and
  `TagDef=".../PlayerMaleTags.xml"`, then selects the weapon sub-ADB by tags.
  It contains named fragments and animation names, including the expected
  `Idle`, `Sprint`, `Sprint_Start`, `Jump`, `Dodge`, `Land`, `Attack`,
  `Block`, `Sheathe`, `Unsheathe`, `Gather`, and weapon-specific fragments.
* No `<Fragment>` or animation record in the extracted player ADBs contains
  the wire numbers `0x07`, `0x0b`, `0x1a`, or `0x1f` as a numeric id field.
  ADB fragment selection is tag-based and is therefore not itself the
  missing numeric lookup.

## Current diagnosis

Both routes reached the same boundary. The binary proves where the client
receives and stores the numeric state, and the paks prove the names/fragments
that the state machine can select. The missing bridge is likely created at
runtime by the CAGE/action-grid loader: a compact id/hash or generated table
is not serialized into the XML names and was not found as a direct string
reference in the executable.

## Driven semantic labels, not recovered numeric mapping

The table below is the complete result of this pass. `VERIFIED` means the name is a runtime semantic observed in the driven traces. An `INFERRED` CAGE candidate is shown only to make the remaining hypothesis explicit; it is not a numeric lookup and must not be used as one.

| layer | id | verified runtime name | CAGE candidate | status |
|---:|---:|---|---|---|
| 0 | `0x1f` | idle | `Idle` | VERIFIED runtime; candidate unverified |
| 0 | `0x1a` | walking | `Nav` | VERIFIED runtime; candidate inferred |
| 0 | `0x0d` | walking -> running | `Nav` | VERIFIED runtime; candidate inferred |
| 0 | `0x0b` | dodge | `Dodge` | VERIFIED runtime; candidate inferred |
| 0 | `0x07` | sprint | `Sprint` | VERIFIED runtime; candidate inferred |
| 0 | `0x1b` | stopping | `Nav_Stop` | VERIFIED runtime; candidate inferred |
| 0 | `0x0e` | jump | `Jump` | VERIFIED runtime; candidate inferred |
| 0 | `0x0c` | landing | `Land` | VERIFIED runtime; candidate inferred |
| 0 | `0x09` | gathering | `Gather` | VERIFIED runtime; candidate inferred |
| 0 | `0x08` | ability | weapon `Ability_*` | VERIFIED runtime; exact candidate unresolved |
| 0 | `0x0a` | attack | `Attack_*` | VERIFIED runtime; exact candidate unresolved |
| 1 | `0x2c` | drawing weapon | `Unsheathe_*` | VERIFIED runtime; exact candidate unresolved |
| 1 | `0x2d` | weapon ready/out | weapon-ready fragment | VERIFIED runtime; exact candidate unresolved |
| 1 | `0x21` | light attack | `Attack_Primary_*` | VERIFIED runtime; exact candidate unresolved |
| 1 | `0x27` | heavy attack | `Attack_Heavy_*` | VERIFIED runtime; exact candidate unresolved |
| 1 | `0x24` | weapon ability | weapon `Ability_*` | VERIFIED runtime; exact candidate unresolved |
| 1 | `0x25` | block | `Block_*` | VERIFIED runtime; exact candidate unresolved |

No row is a verified numeric id-to-CAGE-name mapping. The candidate names come from the extracted `player.grid`, action lists, and ADB XML; several are intentionally generic because the selected weapon and action variant were not recovered. No hash-vs-index conclusion is justified from these rows.
The exact next step is to trace the loader/selection path from
`ActionListComponentSlayerScript` (`0x1448a6261` / `0x1448a63c4`) through
`m_actionGridNew` (`0x144845ee5`) and the `m_slayerScriptName` load
(`0x144846380`), then capture the runtime object that maps the selected
CAGE fragment to its numeric `slayerStateId`. If that path does not reveal a
map, hook the state write/selection call around the known live ids while
forcing `Idle`, `Nav`, `Sprint`, and `Dodge`; log the object pointer, numeric
id, script/fragment string, and layer together. That is the shortest
remaining route to a verified table.

## Reproduction commands

All commands below are read-only. The Ghidra helper serializes access to the project; do not run a second PyGhidra session concurrently.

```sh
NW='/home/andrea/.local/share/Steam/steamapps/common/New World/Bin64/NewWorld.exe'
strings -a -n 4 "$NW" | grep -iE 'slayer|stateId|Idle|Sprint|Dodge|Nav|Crouch|Swim|Sheathe|Block'

.venv-ghidra/bin/python Tools/nw_capture/experimental/offline/ghidra/nw_ghidra.py --script /tmp/cage_postload.py > /tmp/cage_postload.out
.venv-ghidra/bin/python Tools/nw_capture/experimental/offline/ghidra/nw_ghidra.py --script /tmp/cage_strings_specific.py > /tmp/cage_strings_specific.out
.venv-capture/bin/python /tmp/find_rip_refs_one.py > /tmp/find_rip_refs_one.out

python3 - <<'PY'
from pathlib import Path
root = Path('/tmp/newworld-assets-extract/sharedassets/springboardentitites/playerdata/cage')
for path in sorted([*root.glob('*.grid'), *root.glob('*.actionlist')]):
    print(path)
PY
grep -RInE 'slayerStateId|stateId|0x1f|0x1a|0x0d|0x0b|0x07|0x1b|0x0e|0x2c|0x2d|0x21|0x27|0x24' /tmp/newworld-assets-extract/sharedassets/springboardentitites/playerdata/cage /tmp/newworld-player-assets || true
```

The extractor used for the asset route was run as follows; its `pak` variable selects `SharedDataStrm-part7.pak` and its arguments are case-insensitive regular expressions:

```sh
.venv-capture/bin/python /tmp/oodle_extract.py 'sharedassets/springboardentitites/playerdata/cage/player\.grid' 'sharedassets/springboardentitites/playerdata/cage/playeractions_.*\.actionlist'
```

The static field and reader evidence is in `docs/Network/alc-static-analysis.md`; the driven observations are in `docs/Network/pose-state.md`. Temporary outputs are `/tmp/cage-list.txt`, `/tmp/cage_postload.out`, `/tmp/cage_strings_specific.out`, `/tmp/find_rip_refs_one.out`, `/tmp/newworld-assets-extract/`, and `/tmp/newworld-player-assets/`.
