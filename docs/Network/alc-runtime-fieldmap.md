# B - ALCReplicatedState field map from live client tracing

Session: `proton_20260910_163227-alcfieldmap` (75 s, game left running, PID 321407)
Ledger: `Tools/nw_capture/captures/proton_20260910_163227-alcfieldmap/dtls/ledger.bin` (850,374 B)
Copies: `/tmp/nwc/B-ledger.bin`, `/tmp/nwc/B-events.log`, `/tmp/nwc/B-fieldmap.json`
Probe: `/tmp/nwc/B-probe-alc.js`, launcher `/tmp/nwc/B-capture.py`

## Attach route (worked first try, read-only)

Same documented route as `Tools/nw_capture/experimental/offline/capture_with_trace.py`:
`SteamLinuxRuntime_4/run -- "Proton 11.0/files/bin/wine" Tools/nw_capture/frida-server.exe --listen 127.0.0.1:27943`
with `WINEPREFIX=.../compatdata/1063730/pfx`, then `frida.get_device_manager().add_remote_device("127.0.0.1:27943")`,
attach to the single `NewWorld.exe` Windows PID. `rpc.exports.install` armed 5 hooks, no writes to game memory.
Cleanup verified at the end: `pgrep -af frida-server.exe` empty, `ss -ltnp | grep 27943` free, `pgrep -af NewWorld.exe` still shows PID 321407.

## What was hooked

| reader RVA | meaning | ctx | value read on leave |
|---|---|---|---|
| `0x87b5c0` | prefix-coded varint | `args[3]`, cursor `ctx+0x10` | `args[2].readU32()` |
| `0x878610` | bounded raw copy | `args[0]`, `dst=args[1]`, `n=args[2]` | `dst` bytes on leave |
| `0x87a190` | u8 | `args[3]` | `args[2].readU8()` |
| `0x87a1c0` | u16 + order transform | `args[3]` | `args[2].readU16()` |
| `0x87a3d0` | varint-length blob | `args[3]` | length via cursor delta |

Only call sites listed in the task semantics table were kept (allowlist). 52,837 events kept, kinds:
44,182 varint, 8,655 copy. Caller histogram: `0x61ad00f` 11,950; `0x6af237f` 9,063; `0x6af2134` 8,763;
`0x2a4371a` 8,655 (all copy n=1); `0x6ae4541` 5,774; `0x6a6ddda`/`0x6a6de19` 2,780 each; `0x6b079e2` 2,780; `0x2a43265` 292.
No events at all for `0x17b3a90`, `0x17b3670`, `0x6951740`, and no u8/u16/blob events: those call sites did not fire
through these functions in 75 s (see Negatives).

## Frame layer (re-verified live, matches the task description)

Reassembled IN channel-1 stream is 450,308 B; 2,953 frames found with the existing `iter_frames` framing.

```
[marker 00 01 08 01]  offset 0..3
[u32 LE counter]      offset 4..7   (e.g. c3 9b 1b 01 = 18586563, +1 per message)
[01 01 01 00]         offset 8..11
[u16 BE body length]  offset 12..13 (e.g. 00 3c = 60)
[body]                offset 14..
[1-byte trailer]      e.g. 0x4a / 0x5a
```

Live parse event evidence for frame `off=1, counter=18586563` (`seq` is the probe counter, cursors are the
32-bit low half of the ctx cursor; `delta` was constant per buffer, see Log line references):

| seq | caller RVA | cursor in -> out | decoded value | bytes at cursor |
|---|---|---|---|---|
| 1 | `0x6ae4541` | ...936 -> ...937 | 74 (0x4a) | `4a 00 01 08 01 c3` (trailer of previous frame, then marker+counter) |
| 2 | `0x61ad00f` | ...939 -> ...940 | 8 | `08 01 c3 9b 1b 01` |
| 3 | `0x6a6ddda` | ...948 -> ...949 | 0 | `00 00 3c 01 01 10` |
| 4 | `0x6a6de19` | ...949 -> ...950 | 0 | `00 3c 01 01 10 0b` |
| 5 | `0x6b079e2` | ...950 -> ...951 | 60 (0x3c) | `3c 01 01 10 0b 01` |

`0x6b079e2` is therefore reading the body-length low byte (value 60 == that frame's body length), and the
`0x6a6ddda`/`0x6a6de19` pair sits on the length/constant bytes.

## Record layer (VERIFIED against live cursors + ledger bytes)

Every record inside a body was reconstructed from the live parse order. The cursor of each record is
re-based per record (the parser reads each record from its own buffer), so record-relative offsets were
derived from `cursor_in - cursor_in(first event of record)` and cross-checked against the body bytes.

Template, with body offsets from the frame above (`body` = 60 B, starts at stream offset 14):

```
[V1 varint][0x01][V2 varint][0x0b][flag 1|3][payload ...]
```

| record | body off | V1 (reader `0x6af2134`) | 0x01 | V2 (reader `0x6af237f`) | type (reader `0x61ad00f`) | flag (reader `0x2a4371a`, copy n=1) | payload |
|---|---:|---:|---|---:|---:|---:|---|
| 0 | 0 | 1 | @1 | 16 | @3 = 11 | @4 = 1 | off 5..16 (12 B) `ef00016002d49459e03a2778` |
| 1 | 17 | 69 | @18 | 4 | @20 = 11 | @21 = 1 | off 22..28 (7 B) `e300004088a00f` |
| 2 | 29 | 151 (2-byte varint) | @31 | 7 | @33 = 11 | @34 = 1 | off 35..45 (11 B) `fb00000005104d3f390b48` |
| 3 | 46 | 23 | @47 | 4 | @49 = 11 | @50 = 1 | off 51..59 (9 B) `f3000080024d644f2c` |

Live event evidence (same frame): `seq 34` `0x6af2134` rel 0 value 1; `seq 35` `0x6af237f` rel 2 value 16;
`seq 36` `0x61ad00f` rel 3 value **11**; `seq 37` `0x2a4371a` rel 4 copy n=1 byte `01`.
`seq 38..41` repeat at rel 0/2/3/4 -> V1=69, V2=4, type 11, flag 1. `seq 42..45` -> V1=151 (2-byte varint
consumed 2, rel 0->3), V2=7, type 11, flag 1. `seq 46..49` -> V1=23, V2=4, type 11, flag 1.
So the `0x01` between V1 and V2 is a real, always-1 byte not covered by any hooked call site, and the
`0x0b` (= 11 = ALCReplicatedState) is read by `0x61ad00f` in *every* record. The flag byte is always 1 or 3.

Body shapes change between frames (55, 57, 60, 72, 74 ... bytes) because the record set / payload sizes vary;
the record header positions shift accordingly. Machine-readable maps for frames 0, 5, 9, 14, 23 are in
`/tmp/nwc/B-fieldmap.json`.

## Payload layer (PARTIALLY verified)

The payload bytes after the flag are **not** read by any call site in the allowlist; no `0x878610`,
`0x87a190`, `0x87a1c0`, `0x87a3d0` event landed inside a payload in this capture. So the payload is only
known from the ledger bytes, not from a traced reader. Lengths observed: 7, 9, 11, 12 bytes (not the 4..7
of the task hypothesis). The leading payload byte varies (`ef`, `e3`, `fb`, `f3`, `85`, ...); its low bit is
always set, consistent with a presence/bitmask byte, but no interpretation was shown to consume a payload
exactly, so no bit-packed parse is claimed.

## Position screen (NEGATIVE for a verified position)

Criteria checked on payload bytes over the 2,953 frames:

- Smooth monotonic scalar: for record identity `V1=69` (`V2=4`, payload 7 B) the last four payload bytes
  read as big-endian float32 give 4.2695 -> 4.3195 -> 4.3601 -> 4.4100 over frames 0..34, i.e. a smooth
  monotone single scalar. But (a) it is a single scalar, not a pair, (b) the codec has no float32 reader,
  (c) the same last-4-bytes-as-float rule gives physically impossible values for `V1=23` (2.4e8) and
  `V1=151` (7.3e9 then 4.1e11) and for `V1=1` (-5.4e19), so the float reading is not a consistent schema.
  I am not reporting it as a position.
- Monotone non-decreasing tails: the last four payload bytes of the frequent records are non-decreasing for
  731/741 (`V1=1`), 675/683 (`V1=23`), 880/881 (`V1=69`), 970/977 (`V1=151`) consecutive samples. This is
  consistent with a delta-replicated value that only changes when it moves, but it is equally consistent
  with several other monotone quantities and no two-field (x,y) pair passes, so it is **inferred, not
  verified**.
- `+1`/`+N` revision counter (`idRel` calibration): none of the captured varint fields increments by exactly
  +1 per frame. The only strictly +1 sequence is the frame `u32 counter` in the frame header, which is a
  stream counter, not a replicated field. So the record field order was not calibrated by a revision counter.
- Teleport: no single-field large jump followed by stability was isolated; the payload tail changes happen
  in place while the record set is stable (frames 5..13, 14..22, 23..), which looks like ordinary updates,
  not a teleport.

**Conclusion: the reconstruction of the ALCReplicatedState record layout is verified; the player position
field is NOT identified.** The most likely place is the post-flag payload, and the exact payload reader was
not captured because its call site is not in the provided semantics table (see next).

## Negatives / what was not captured

- No varint/u8/u16/blob events from the likely payload readers `0x17b3a90`, `0x17b3670`, `0x6951740`; a
  probe that logs those readers without the caller allowlist (or hooks the type-11 handler directly) is the
  next step to see the payload field values.
- Caller `0x2a4371a` is a bounded copy `0x878610(n=1)`, not the u8 reader; flag values seen are only 1 and 3.
- The 1-byte `0x01` between V1 and V2 in every record is not read by any hooked primitive.
- No `0x87a190`/`0x87a1c0`/`0x87a3d0` calls fired through the allowlisted callers in 75 s.

## Verified vs inferred

VERIFIED (live cursors + ledger bytes agree):
- Frame layout and the readers on the frame header (`0x6ae4541`, `0x6a6ddda`, `0x6a6de19`, `0x6b079e2`).
- Record template `[V1 varint][0x01][V2 varint][0x0b][flag 1|3][payload]` and the reader RVAs
  `0x6af2134` (V1), `0x6af237f` (V2), `0x61ad00f` (type ref = 11), `0x2a4371a`+`0x878610(1)` (flag).
- Type ref 11 (ALCReplicatedState) on every one of the reconstructed records.
- Payload boundaries for the sample bodies (cursor deltas match body bytes exactly).
- Capture hygiene: game alive, no frida-server, port free.

INFERRED / NOT VERIFIED:
- Meaning of V1/V2, the `0x01` byte, and the payload bits.
- Any position field. Monotone payload tails are candidates only.
- Float interpretation of payload tails (rejected as a schema).
- Payload reader function/call site (not captured).
