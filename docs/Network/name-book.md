# The name book: wire ids are crc32 of the datasheet ids

Status 2026-09-11: VERIFIED on cooldowns, mounts, perks, items, status effects, vitals rows and titles.

## The convention

Every opaque 32-bit id we met on the wire is `crc32(id.lower())` of a datasheet string id
(`zlib.crc32`, standard polynomial, the string lower-cased, no terminator). Evidence in the order it
was found:

| state | ids seen | resolve to | sheet |
|---|---|---|---|
| CooldownTimers 2932 | `9d35d4b6`, `65dd6ce5`, `b4885352`, `1b0fa511`, `473ac2ed`, `a4f1ef53`, `aa35c6fa` | `Ability_VoidGauntlet_Scream`, `_NullChamber`, `_VoidBlade`, `Ability_Blunderbuss_SplittingGrenade`, `_AzothShrapnelBlast`, `_NetShot`, `Ability_Rapier_Riposte` (7 of 7) | weaponabilities |
| Mount 5620 | `e4fdfda0`, `a241760c`, `5b3a4c4b`, `4f1bd9c5` | `Mount_Horse_1`, `Mount_MTX_bear_Panda`, `Mount_Wolf_4`, `Mount_MTX_lion_CosmicPanther` | mounts, entitlements |
| AbilityComponent 185 | `3ab603a5`, `124e16b9`, ... | `Global_Perk_StatSwap_Health`, `Ability_Perk_Amulet_HP` (equipped perks) | perks |
| Paperdoll 3183 | many | `2hGreatAxeLostT5` = Forsaken Great Axe, appearance ids | itemdefinitions_* |
| StatusEffects 4236 | many | `MinersResolveLSB` = Miner's Resolve, ... | statuseffects_* |
| Vitals 15 full state | offsets 42 and 46 | `Player`, `Wolf_Grey_6`, `Turkey`, `Boar_6`, `Risen_L-R_Arm_6` | vitalscategories, vitalstables |
| Social 4176 | many | `PlayerTitle_OutpostRush_Score_Top10` = Outpost Rush Medalist | playertitles |

The case matters: `crc32("Ability_VoidGauntlet_Scream")` is `8831cfa0`, the lower-cased string gives
the wire value `9d35d4b6`.

## Tools (`Tools/nw_assets/`)

- `pak_extract.py list|get PATTERN...`: the .pak files are zip containers; method 0 is stored, method 15
  is Oodle. The decompressor is third-party and stays out of the repository:
  `private/tools/oodle/liboo2corelinux64.so.9` (`NW_OODLE_LIB` to override). Output under
  `private/assets/` (gitignored). The game install is read only.
- `datasheet.py FILE [--csv] [--grep]`: the binary datasheet (layout from new-world-tools):
  15-u32 header, column and row counts, column index (crc32, name offset, type 1 string / 2 number /
  3 bool), cells (offset, value), string pool relative to `60 + body offset`. Checked on
  `javelindata_mounttypes` (109 columns, 6 rows) and used on 2,250 sheets.
- `namebook.py build`: extracts `datatables/**/*.datasheet` (2,250 sheets, 215 MB) and
  `localization/en-us/*.loc.xml` (184 files), then writes `private/assets/namebook.json`:
  `{"9d35d4b6": {"id": "Ability_VoidGauntlet_Scream", "sheet": "ability_voidgauntlet", "column":
  "AbilityID", "display": "@VoidGauntlet_Ability_Scream", "text": "Petrifying Scream"}}` for every
  identifier-looking string cell: 265,451 ids, 102,479 with an English text. The sheet that carries a
  display name for a row wins over one that only references the id. `namebook.py lookup HEX...`.
- `nw_live.py` loads the book at start (`NAMES`), resolves ids with `name_of()` / `text_of()`, and reads
  Paperdoll, StatusEffects, Social and the Vitals ids by scanning 4-byte windows of the payload against
  the book, filtered by sheet (`book_hits`). ponytail: with 265k ids a stray window matches with
  probability 6e-5; the sheet filter and the tuple cache keep it honest and fast. Field tables replace
  the scan the day a false name shows.

## Field layouts read along the way

Vitals full state (member 0, field mask `ff`, then a second `ff` mask byte for fields 8..15; see
`decode_vitals.parse_full_state`): health f32 at 2, a 100/110 float at 6 on players and 0 on
non-players (the player/companion discriminator), `HealthBaseMax` f32 at 29 (equals the max health of
every mob checked: Grey Wolf 609, Turkey 16, Boar 639, Withered 548; players sit above it), a
100/1.0 float at 35 (mana base max), `vitalsId` crc at 42, `vitalsCategoryId` crc at 46, `vitalsLevel` u32
at 50 and two flag bytes at 54 on the 56-byte mob payload. The property names
`vitalsId`, `vitalsCategoryId`, `vitalsLevel`, `invulnerability` sit in `.rdata` next to
`HealthAmount` (`0x14855F7B0`).

ProgressionComponent 899: member 0 bit 0 u32 = level (12 -> 1,066 hp, 69 -> 18k hp).
FactionComponent 3152: member 2 bit 0 u8 = faction id; `javelindata_factiondata` rows Faction1..3
carry `FactionIntro_Syndicate/Marauders/Covenant_Recruitment`, so 1 Syndicate, 2 Marauders, 3 Covenant.
AttributeComponent 129: `01 0f`, u32 count 5, then (id u32, points u32) pairs, ids 4..0; the attribute
sheets are ordered STR, DEX, INT, FOC, CON and the player's 225 sat on id 3 with a life staff + void
gauntlet kit (Focus).
ManaComponent 1652 and StaminaComponent 4297 share one shape: six f32 BE in bit order (amount, max,
winded countdown, regen delay, two multipliers).
StatMultiplierTable 1525: `06 07`, then (u16 stat id, u32 basis points) entries, 10000 = 1.0x; a
buff moved one to 11500 and another to 20000. The stat ids are an enum, not crc32: unnamed.
PositionInTheWorld 13: `01 03`, f32 x, f32 y, then 5 bytes (a u16, `03`, a u16); the spawn position,
kept by the viewer for entities without an ALC track.
GdeMetadata 10: `01 03`, a 16-byte uuid, `00000002`, a second uuid; the first uuid appears in
`Engine.pak/assetcatalog_optimized.catalog` (magic `RAOC`), whose record format was not decoded.
