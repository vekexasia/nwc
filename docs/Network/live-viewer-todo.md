# Live viewer: what goes in next

Checklist for `nw_live.py` / `nw_live.html`, in order. Every item is fed by a state that already appears
in our join logs, so each one is decode + wiring + a check, no new reverse-engineering entry point.
Tick an item only when it shows in the page from a live capture.

| # | factor | source state | status |
|---|---|---|---|
| 1 | pose / action label (idle, walk, run, dodge, sprint, attack, weapon out) | ALC `slayerStateId` layers 0 and 1, table in [pose-state.md](pose-state.md) | done, `511ed84` |
| 2 | facing arrow on the marker | ALC `rotation`, smallest-three quaternion (`FUN_14087a8d0`), heading = yaw + 90 checked on two walks | done |
| 3 | damage feed (taken, per entity) | Vitals health deltas. `DamageReceiverComponent` 1528 turned out to be flags (`01 03 00 00 00 00 20/34/37`, `01 01 00/01`), not events; the per-hit RMI `OnDamageDealt` is a channel-0 message our probe does not log | done, from Vitals |
| 4 | mob names on the grey markers | `PlayerNameTagComponentReplicatedState` 100 carries `01 01 00000001` only: a flag, no string. Mob names are not replicated; the client resolves them from the spawn row (`VitalsComponent.m_rowReference`), i.e. datasheets | done via the name book: the Vitals full state carries the vitals row id, `Black Boar`, `Grey Wolf`, `Withered Punisher` |
| 5 | mounted yes/no | `MountComponentReplicatedState` 5620, driven mount 14:23:15 and dismount 14:27:59: owner member 1 bit 0 / bit 4 flag (+ a ns timestamp) and bit 6 mount stamina; remote players member 2 mount id (0 when dismounted). `decode_mount.py` | done |
| 6 | equipment / weapon of nearby players | `PaperdollComponentReplicatedState` 3183 item ids resolved by the name book (`Icebound Ice Gauntlet`, `Legion Spear`); shown as the row tooltip and the HUD gear line | done |
| 7 | elevation in metres | ALC `worldPosAbs` u16 in [-100, 1000] (`-100 + q*1100/65535`, the mapping of `decode_position.py`, median 1.38 from the markers) | done |
| 8 | true max health | not replicated in Vitals deltas (member 0 = health f32 + a 1-byte flag: 03 damage, 01 regen at +43.9/s); `AttributeComponent` 129 carries the attribute points (CON 225), not the derived max. The bar keeps the highest value seen | closed: max seen |

Done before this list: position, names, health, mana (Vitals), stamina (4297), cooldowns (2932),
entity join (`e<V1>`), `e1` = player.

Added after the list, all through the name book (`Tools/nw_assets/namebook.py`: crc32 of the
lowercase datasheet id, English text from the localization files): cooldown ability names, mount
names, player level (899), faction (3152: 1 Syndicate, 2 Marauders, 3 Covenant), status effects
(4236), player vs companion (Vitals member 0 bit 1), gathering flag (2930), stance byte, facing wedge,
damage feed, capture start/stop from the page.

Added on 2026-09-11 evening through the RMI stream (`rmi_samples`, [rmi-messages.md](rmi-messages.md)):
chat above the feed, per-hit damage taken and dealt with damage type names, the target of a dealt hit
(bound by the equal health delta), the player's own name (chat line from the self uuid), attributes
fixed (five (points, id) pairs). Still not shown for e1: the equipped weapons (the own paperdoll
carries item instances, not definition ids; the inventory stream `ItemVersionData`/`JsonItemData`
is cut at 160 bytes by the probe).

Still open: the numeric slayer state ids have no table in binary or assets
([pose-state-names.md](pose-state-names.md)); the player's own HealthMax (the Vitals full state gives
`HealthBaseMax`, exact for mobs, below the live max for players); StatMultiplierTable stat ids are an
unnamed enum. Static entities (13)
are on the map as squares since `9306949`; the Vitals full state is read to the byte
([name-book.md](name-book.md)).

Method per item, the one that worked for stamina and cooldowns: (a) pull the player's chunks of that
type from an existing join log, (b) read the shape by hand against a driven or known action, (c) a
`decode_<x>.py` with `--check` on the real bytes, (d) `apply_line` in `nw_live.py`, (e) the page,
(f) a headless-Chromium screenshot as the proof.
