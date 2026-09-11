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

Layers matter: the four `slayer*` triplets (reader bits 13..24) are four layers, and the timeline
prints them as `[L0]`..`[L3]`. Layer 0 is locomotion, layer 1 is the weapon. Times are key-press
time -> first frame with the new state (the hook stamps arrive 0.1-0.15 s after the key).

| layer | `slayerStateId` | when | evidence |
|---|---:|---|---|
| L0 | `0x1f` (31) | idle; entered 1.3-2 s after stopping, `slayerSequenceId` `0xbb0f` every time | all runs |
| L0 | `0x1a` (26) | `w` pressed: walk start, `slayerSeqTimeAbs` reset; sequence `0x8b1d`; comes back with sequence `0xaa2f` during a sprint | poseA 11:47:03.9 / 09.1, joinwalk 11:25:22.4 |
| L0 | `0x0d` (13) | ~0.5 s into a `w` hold, sequence `0x8b1a`: walk -> run transition (the speed byte `group1.bit0` peaks at 0x5a) | poseA 11:47:04.4, 10.9, 12.2 |
| L0 | `0x0b` (11) | right after a `shift` tap while moving (dodge), sequence `0x962d`, held ~1 s | poseA 11:47:04.8 (key 04.83), 10.9 |
| L0 | `0x07` (7) | `shift` held while moving: sprint start, sequence `0xad4b`; `group0.bit44` starts counting up each 150 ms while sprinting | poseA 11:47:10.2 (key 10.04) |
| L0 | `0x0c` (12) | once, mid-sprint, sequence `0xa146` (unknown sub-state) | poseA 11:47:12.2 |
| L0 | `0x1b` (27) | keys released while running: coming to a stop, ~1.3 s, then `0x1f` | poseA 11:47:13.2, actions2 08:22:34.5, alcdodge 18:31:27 |
| L0 | `0x0e` (14) | `space`: jump, sequence `0xb30a`, back to `0x1f` after 1.8 s | poseA 11:47:00.7 (key 00.62) |
| L1 | `0x2c` (44) | `1` pressed: weapon draw, sequence `0x881d`, 0.7 s | poseA 11:47:16.2 (key 16.05) |
| L1 | `0x2d` (45) | weapon ready; re-entered with sequence 0 and a new `slayerStateIdStarted` on each cast (`q`, `r`) and after every attack | poseA 11:47:16.9, actions2 08:22:39.2 / 42.2, alchit, poseB |
| L1 + L2 | `0x21` (33), seq `0x61`; L2 `0x2e` seq `0xa006` | left click (light attack): 0.9 s, then L1 back to `0x2d` and L2 to 0 | poseB 11:49:54.2, 11:50:01.0 |
| L1 | `0x27` (39), seq `0x60` | left held 1.2 s (heavy attack): follows `0x21`, 0.6 s, then `0x2d` | poseB 11:50:01.8 |
| L1 + L2 | `0x24` (36), seq `0x8142` -> `0x9842` -> `0x9142`; L2 `0x2e` seq `0x9806` | right held 2 s (weapon RMB ability): sequence advances while held, `0x2d` on release | poseB 11:50:08.8 - 10.9 |

Observed by the player on the live page (14:37-14:41, weapon of that moment, ids are per weapon
script): L0 `0x0a` attack, L0 `0x08` ability, L1 `0x25` block. Repeated jumps show `0x0e` -> `0x0c` ->
`0x1a`: `0x0c` is the landing, not a sprint state as first written.

**Crouch and prone are not states.** They are sequences inside idle (`slayerSequenceId[L0]` `bf36` ->
`bc3b` crouching, `822f` -> `aa3f` going prone, `a33f` standing) and a stance byte, `group0.bit43`:
`0x89` crouched, `0x49` prone, `0x09` standing (bits 0x80 and 0x40 on top of a base 0x09). The viewer
reads the stance byte.

Layer 2 is set only during an attack (`0x2e`, two sequences seen), so it looks like the attack or
hit-volume layer; layer 3 never changed. Open: the sub-state `0x0c`, the `0x1a/0xaa2f` return inside a
sprint, and the names of the clips, which are in the assets, not here.

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

Still to drive, one per capture with the join probe: block, weapon sheathe, mount, swim, emotes,
and the same actions with a second weapon to see whether the L1 ids are per weapon. Then the asset side: `slayerStateId` -> slayer script ->
clip, from the game files (nw-buddy), which is what a server would need to pick a state on purpose.
