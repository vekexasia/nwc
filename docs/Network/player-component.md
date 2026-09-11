# PlayerComponentReplicatedState: the field table and how to read it live

typeIndex 3935, registry index 3160, uuid `BDDDA784-A6E7-416B-A041-449920D90FB6`, `Unmarshal`
`NewWorld+0x6573d60`, `CreateInstance` `NewWorld+0x6573b80`.

This is the state that carries who an entity is: character id, character name, home world, platform
account. It is the missing piece for attributing a position or a Vitals object to a player without a
heuristic.

## How the table was recovered

`Unmarshal` is four lines long and goes through the same generic path as Vitals:

```c
longlong FUN_146573d60(undefined8 param_1, longlong param_2, undefined8 param_3, undefined8 param_4)
{
    puVar1 = (undefined8 *)FUN_146711e90(param_3);      // the state's builder
    FUN_146160ae0(puVar1, param_2, param_4);            // the shared three-stage deserialiser
    ...
}
```

`FUN_146160ae0` is the deserialiser already documented for Vitals (`+0x90` mask-driven members,
`+0xa0`, `+0xb0`), so this state is a plain replicated state and not a schema-builder one. The field
table comes from the **31 registration calls** in the builder `FUN_146711e90`, each of the form
`FUN_141775c60(state, <name>, state + <offset>, <flag>)`, where `<name>` is a pointer to a real string
in `.rdata` (unlike `PlayerComponent`'s name itself, these property names **are** in the executable).

Registration order is the member order, as for Vitals.

| # | offset | field | # | offset | field |
|---|---|---|---|---|---|
| 0 | `+0x7c0` | `characterId` | 16 | `+0xd48` | `sessionStartTimePoint` |
| 1 | `+0x870` | `characterName` | 17 | `+0xd90` | `debugAccountProbationOverride` |
| 2 | `+0x8f0` | `homeWorldId` | 18 | `+0xdb0` | `freePlayerCountdown` |
| 3 | `+0xac8` | `playerConnected` | 19 | `+0xc28` | `enteringStoreIsBlocked` |
| 4 | `+0xae8` | `lookingThroughLoadout` | 20 | `+0xc48` | `isFreshStartWorld` |
| 5 | `+0xc68` | `playerType` | 21 | `+0xe08` | `onDeathRespawnCooldown` |
| 6 | `+0xb08` | `isInStore` | 22 | `+0xed0` | `mostRecentPVPActiveSwitchTimePoint` |
| 7 | `+0xe58` | `platformAccountId` | 23 | `+0xf18` | `shouldNotifyPlayer` |
| 8 | `+0xe90` | `platformType` | 24 | `+0xeb0` | `isPVPActiveCharacter` |
| 9 | `+0xa50` | `loginMatchId` | 25 | `+0xb28` | `isChangingMount` |
| 10 | `+0x9a0` | `srcWorldId` | 26 | `+0xb48` | `isTransmogStationScreenOpen` |
| 11 | `+0xbc8` | `accountIsLocked` | 27 | `+0xb68` | `isTransmogScreenOpen` |
| 12 | `+0xbe8` | `accountInProbation` | 28 | `+0xb88` | `isInMountAttachmentMode` |
| 13 | `+0xc08` | `ageGroup` | 29 | `+0xba8` | `isArmorDyeingOpen` |
| 14 | `+0xc90` | `territoryOwnerGuildId` | 30 | `+0xe30` | `playerBackstory` |
| 15 | `+0xd00` | `sessionStartWallClockTimePoint` | | | |

Cross-check against the community's own decode of a spawn bundle
(`private/open-world-discord/attachments/105_message.txt`, 29 fields, their tooling and their build):
their `character_name`, `player_type` and `platform_account_id` line up with `characterName`,
`playerType` and `platformAccountId`, in the same relative order. Two independent decodes agreeing on
three names is the strongest evidence available for this state.

## Reading it live

`Tools/nw_capture/experimental/nw_player_probe.js` hooks the builder (RVA `0x6711e90`), takes its first
argument as the state pointer, and reads the fields 150 ms later, once the deserialiser has filled the
object. Read-only.

Verified: a 20 second capture (`Tools/nw_capture/logs/20260911-094221_player2.log`) observed **21
PlayerComponent states**, and the character names came out as real player names (`stormvind`,
`Warrior3`, `Eins Fas ttv`).

`characterName` is not a raw string: the first qword of the field is a pointer into `.rdata` and the
characters start 16 bytes in. Read up to the first non-printable byte from `field + 0x10`.

## Still open

- The **type and wire width of each field**. `characterId`, `homeWorldId`, `srcWorldId`,
  `platformAccountId` and `loginMatchId` are structures, not plain integers (their first qword is a
  type/vtable pointer), so reading them needs the codec, not a fixed-width load. The brute-force dump
  in the probe is a placeholder.
- **Linking a PlayerComponent to the other states of the same entity** (ALC for position, Vitals for
  health and mana). The replica/entity id is in the bundle header, not inside these states, so the
  link has to come from the bundle order observed at runtime or from a field that carries the same id.
  Until then, identity and position are read but not joined.
- Whether the state appears only on create or also as an update member.
