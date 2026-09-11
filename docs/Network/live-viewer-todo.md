# Live viewer: what goes in next

Checklist for `nw_live.py` / `nw_live.html`, in order. Every item is fed by a state that already appears
in our join logs, so each one is decode + wiring + a check, no new reverse-engineering entry point.
Tick an item only when it shows in the page from a live capture.

| # | factor | source state | status |
|---|---|---|---|
| 1 | pose / action label (idle, walk, run, dodge, sprint, attack, weapon out) | ALC `slayerStateId` layers 0 and 1, table in [pose-state.md](pose-state.md) | done, `511ed84` |
| 2 | facing arrow on the marker | ALC `rotation`, smallest-three quaternion (`FUN_14087a8d0`), heading = yaw + 90 checked on two walks | done |
| 3 | damage feed (dealt / taken) | `DamageReceiverComponentReplicatedState` 1528 | todo |
| 4 | mob names on the grey markers | `PlayerNameTagComponentReplicatedState` 100 | todo |
| 5 | mounted yes/no | `MountComponentReplicatedState` 5620 | todo |
| 6 | equipment / weapon of nearby players | `PaperdollComponentReplicatedState` 3183 | todo |
| 7 | elevation in metres | ALC `worldPosAbs` u16, affine fit on the community markers | todo |
| 8 | true max health | not in Vitals members 0/1; try `AttributeComponent` 129, `StatMultiplierTable` 1525 | todo |

Done before this list: position, names, health, mana (Vitals), stamina (4297), cooldowns (2932),
entity join (`e<V1>`), `e1` = player.

Method per item, the one that worked for stamina and cooldowns: (a) pull the player's chunks of that
type from an existing join log, (b) read the shape by hand against a driven or known action, (c) a
`decode_<x>.py` with `--check` on the real bytes, (d) `apply_line` in `nw_live.py`, (e) the page,
(f) a headless-Chromium screenshot as the proof.
