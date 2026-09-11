# Entity join: the record header V1 groups the states of one entity

Status 2026-09-11: VERIFIED live on three captures plus one driven walk. This closes the open item
"position, health and name live in different objects with no common key".

## The record layer, read from the code

`FUN_146af20d0` (RVA `0x6af20d0`) is the record reader hooked as "V1 varint" in earlier probes:

```
V1      prefix varint (FUN_14087b5c0) -> written as u16 to the caller's out parameter (args[1])
count   u8, the constant "0x01" of the old grammar: it is the number of chunks that follow
chunk*  FUN_146af2340 (RVA 0x6af2340), `count` times:
          V2        prefix varint (u32)
          type ref  FUN_1461ad130 -> FUN_1461acfe0: typeIndex varint (0 = 16 inline uuid bytes)
          object    created by the type's factory, then object->vtable[0x90](object, ctx)
                    consumes exactly that state's payload
          push {u32 V2, +8 object, +16 control block} (24 bytes) on the vector at args[1]
```

The reader context is `*args[0]`, cursor at `ctx+0x10`, as for every other reader. The varint
primitives take `(ret, &status, &value, ctx)`: the value is behind **args[2]**, not args[0]. The earlier
join attempt read a window at `args[0]+0x10` and saw a constant; that was the return slot.

## What the values are (VERIFIED on the wire)

- **V1 is the entity key.** All chunks that share a V1 belong to one entity: a mob carries
  `ALCReplicatedState` (11), `VitalsComponentReplicatedState` (15), `DamageReceiverComponent` (1528),
  `PaperdollComponent` (3183) and others under one V1, with a coherent position track and a plausible
  health (548, 628, 708, 1522 in one town capture). V1 is stable within a session
  (`Tools/nw_capture/logs/20260911-111610_join2.log`, `..._112222_join3.log`).
- **V2 is the chunk slot inside the entity**: ALC sits at V2 16 for players and 5 for the mobs seen,
  the other states at 0, 3, 6, 10, 17..25. It is not an entity id.
- **V1 = 1 is the local player.** In four captures over two days the first record of every body is
  `(V1 1, V2 16, type 11)`. A 4 s driven walk (`nw_vkeys.py --seq w:4`, 11:25:20-11:25:24) moved
  exactly one entity only inside that window: `e1`, from (9352.5, 2677.6) to (9351.0, 2673.3), at
  0.5 s intervals, nothing before or after; every other moving entity kept moving after the key was
  released (`20260911-112506_joinwalk.log`). V1 = 1 is also the only entity carrying the owner-only
  states (Interactor 3752, StatMultiplierTable 1525, AbilityComponent 185). One walk, one session:
  re-check with the same probe if a capture ever starts with another V1 first.
- **The object pointer pushed on the vector is transient**: the same address served every ALC chunk
  of every entity in one capture. It is a value object the game applies to the entity afterwards, so
  it is not a join key, and the "objects" of the earlier live view were never entities.
- **The chunk length is exact per type**: `cursor_after - cursor_before` of `FUN_146af2340` is the
  wire length of `V2 + type + payload`. Every ALC payload in the three captures decoded exactly with
  `decode_record_payload` (no `alc_inexact`), and the per-type length table printed by
  `decode_join.py` is the record-length oracle the TODO asked for, with no static analysis.

## Tools

- `Tools/nw_capture/experimental/nw_join_probe.js`: hooks the two record functions and the
  `worldPosAbs` reader. Emits `join_samples` (`[ts, V1, V2, typeIndex, object, payload_len,
  payload_hex, name?]`) as the raw evidence, and the three shapes `nw_live.py` already reads
  (`pos_samples`, `vitals_samples`, `player_samples`) keyed by entity `e<V1>`, so the live view shows
  position, health and name joined without a change on its side. The name is emitted only from a
  full PlayerComponent state (entity entering scope); delta chunks carry none.
- `Tools/nw_capture/experimental/offline/decode_join.py --log <log>`: entities with their types,
  track, health and name, then the payload-length table. `--check` is the runnable check.

```sh
.venv-capture/bin/python Tools/nw_capture/experimental/nw_capture_probe.py \
    --probe "$PWD/Tools/nw_capture/experimental/nw_join_probe.js" --seconds 45 --label join
.venv-capture/bin/python Tools/nw_capture/experimental/offline/decode_join.py \
    --log Tools/nw_capture/logs/<run>_join.log
```

## Limits

- Names and full states arrive once, when an entity enters scope. An entity already in scope when the
  capture starts has no name until it leaves and returns; the live view has to keep the V1 -> name
  map for the whole session.
- V1 is a per-session value. Nothing here says whether it is the GridMate replica id or a bundle-local
  index; only that it is the key the client uses to route chunks to one entity.
- Type references with index 0 (16 inline uuid bytes) are parsed as typeIndex 0 with a 16-byte shift
  in the payload; none was seen in these captures.
