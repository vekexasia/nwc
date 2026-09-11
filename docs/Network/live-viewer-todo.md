# Live viewer: what goes in next

Checklist for `nw_live.py` / `nw_live.html`, in order. Every item is fed by a state that already appears
in our join logs, so each one is decode + wiring + a check, no new reverse-engineering entry point.
Tick an item only when it shows in the page from a live capture.

| # | factor | source state | status |
|---|---|---|---|
| 1 | pose / action label (idle, walk, run, dodge, sprint, attack, weapon out) | ALC `slayerStateId` layers 0 and 1, table in [pose-state.md](pose-state.md) | done, `511ed84` |
| 2 | facing arrow on the marker | ALC `rotation`, smallest-three quaternion (`FUN_14087a8d0`), heading = yaw + 90 checked on two walks | done |
| 3 | damage feed (taken, per entity) | Vitals health deltas. `DamageReceiverComponent` 1528 turned out to be flags (`01 03 00 00 00 00 20/34/37`, `01 01 00/01`), not events; the per-hit RMI `OnDamageDealt` is a channel-0 message our probe does not log | done, from Vitals |
| 4 | mob names on the grey markers | `PlayerNameTagComponentReplicatedState` 100 carries `01 01 00000001` only: a flag, no string. Mob names are not replicated; the client resolves them from the spawn row (`VitalsComponent.m_rowReference`), i.e. datasheets | blocked: asset side |
| 5 | mounted yes/no | `MountComponentReplicatedState` 5620, driven mount 14:23:15 and dismount 14:27:59: owner member 1 bit 0 / bit 4 flag (+ a ns timestamp) and bit 6 mount stamina; remote players member 2 mount id (0 when dismounted). `decode_mount.py` | done |
| 6 | equipment / weapon of nearby players | `PaperdollComponentReplicatedState` 3183: per slot an item id, a perk hash list and a 16-byte instance id (full state 1947 B at spawn, 9..480 B deltas). Names need the item datasheets (nw-buddy) | blocked: asset side |
| 7 | elevation in metres | ALC `worldPosAbs` u16 in [-100, 1000] (`-100 + q*1100/65535`, the mapping of `decode_position.py`, median 1.38 from the markers) | done |
| 8 | true max health | not replicated in Vitals deltas (member 0 = health f32 + a 1-byte flag: 03 damage, 01 regen at +43.9/s); `AttributeComponent` 129 carries the attribute points (CON 225), not the derived max. The bar keeps the highest value seen | closed: max seen |

Done before this list: position, names, health, mana (Vitals), stamina (4297), cooldowns (2932),
entity join (`e<V1>`), `e1` = player.

Method per item, the one that worked for stamina and cooldowns: (a) pull the player's chunks of that
type from an existing join log, (b) read the shape by hand against a driven or known action, (c) a
`decode_<x>.py` with `--check` on the real bytes, (d) `apply_line` in `nw_live.py`, (e) the page,
(f) a headless-Chromium screenshot as the proof.
