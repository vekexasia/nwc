# Pose on the wire: the slayer state fields of ALCReplicatedState

Status 2026-09-11: PRELIMINARY. The fields are decoded exactly (they are part of the ALC payload that
consumes to the byte), the meaning of the values below rests on one driven walk and one scripted
action run. Nothing here names an animation clip: that mapping lives in the game assets.

## What the server sends

The pose is not a skeleton. Per entity and per layer (4 layers, reader-vector bits 13..24, see
`alc-protocol-reference.md` 2.4 and 3.2) the ALC record carries:

| field | wire | what it does in the traces |
|---|---|---|
| `slayerStateId` | prefix varint | the state of the slayer script state machine; changes on walk start, stop, cast |
| `slayerStateIdStarted` | u16 | a stamp that grows with time (0x4452 -> 0x44eb over 8 s, 0x5541 -> 0x5597 over 6 s): when the state started |
| `slayerSequenceId` | prefix varint | the sequence inside the state; changes without a state change when the walk stops |
| `slayerSeqTimeAbs` | half float | seconds since the sequence started; resets to ~0.05 on a new state, then +1.0 per second |
| `slayerSeqTimeRel` | u8 -> float | present in every frame; the per-frame time delta of the sequence |

The client resolves `slayerStateId` through the slayer script assets to a clip and plays it at
`slayerSeqTime`. Replicating a pose from a server therefore means sending these fields with a valid
`idRel`/`timeOffsetRel` heartbeat, not bones.

## State ids seen for the player (V1 = 1)

| `slayerStateId` | when it appeared | evidence |
|---:|---|---|
| `0x1a` (26) | walk start (`w` held), `slayerSeqTimeAbs` reset to 0.05 | `logs/20260911-112506_joinwalk.log` 11:25:22.4, `captures/proton_20260910_183044-alcdodge` 18:31:09 |
| `0x1b` (27) | sprint end / coming to a stop, held for ~1.3 s | `captures/proton_20260911_082212-actions2` 08:22:34.5 (timeline `sprint_end`), alcdodge 18:31:27 |
| `0x1f` (31) | idle, entered 1.3-2 s after stopping, `slayerSequenceId` `0xbb0f` each time | actions2 08:22:35.9, joinwalk 11:25:28.6, alcdodge 18:31:29 |
| `0x2d` (45) | each spell cast (`cast1`, `cast2`), `slayerSequenceId` 0, and the two hits of `alchit` | actions2 08:22:39.2 and 08:22:42.2, `captures/proton_20260910_231300-alchit` |

Also moving with the pose but not named: `group0.bit37` (2 bytes, `c500`/`c000`/`0000`, the TODO
calls it `segmentedStamina`), `group0.bit41` (1 byte, `e3`/`f3` toggling while moving) and
`group1.bit0` (1 byte, rises 0 -> 0x11 in the first second of a sprint and decays on stop: looks like
a speed or blend parameter). Do not name them without a driven test.

## How to read it

From a join-probe log (any entity) or straight from a capture ledger (player only, no probe needed):

```sh
.venv-capture/bin/python Tools/nw_capture/experimental/offline/decode_join.py \
    --log Tools/nw_capture/logs/<run>_join.log --timeline 1
.venv-capture/bin/python Tools/nw_capture/experimental/offline/decode_join.py \
    --ledger Tools/nw_capture/captures/<session>/dtls/ledger.bin --timeline 1
```

The ledger route works because the player's ALC record is the first record of every body; it prints
nothing on ledgers whose channel-1 stream does not frame with the known grammar
(`proton_20260911_105731-walktest`, `..._081033-jump`, `..._091552-dodge` in this tree).

## Next

Drive one action per capture with the join probe running (jump, dodge, sprint start, light attack,
heavy attack, weapon draw/sheathe, mount) and add the rows. `nw_actions.py` writes a timeline that
lines up with the output above; the sprint start itself produced no state change in `actions2`,
only the `group1.bit0` ramp, so sprint may be a sequence inside state `0x1a` rather than a state.
