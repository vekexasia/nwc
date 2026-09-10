# ALCReplicatedState: protocol and field reference

Reference for the inbound replication class we decode today. Everything here was read out of the
running client or the binary with the tools listed at the end; the raw evidence lives in
[alc-static-analysis.md](alc-static-analysis.md) (Ghidra) and
[alc-runtime-fieldmap.md](alc-runtime-fieldmap.md) (live tracing), and the chronological research
log in [offline-framing-findings.md](offline-framing-findings.md).

Convention: **VERIFIED** = read in the code, the bytes or a live trace, with the address or the
measurement given. **INFERRED** = a conclusion that goes beyond that. Anything marked INFERRED is
safe to revisit, anything marked VERIFIED should not be re-litigated without new evidence.

Build note: all addresses are RVAs into the installed `NewWorld.exe` (image base `0x140000000`),
which matches the community's registry dump (3484 of its 3487 uuids appear verbatim in this file).

---

## 1. Layer stack

```
DTLS 1.2 record (SSL_read hook, plaintext captured by the repo's ledger)
  └─ Carrier datagram: 4-byte header, LZ4 when the mode bit is set     [decode_dtls_ledger.py]
       └─ channel-1 stream, per direction                              [reassemble_channel_messages]
            └─ frame: marker + counter + 4 bytes + u16 length + body + varint trailer
                 └─ record: V1 + 0x01 + V2 + type-ref + group mask + grouped payload
                      └─ payload: ALC field framing (group mask, field mask, field readers)
```

### 1.1 Frame (VERIFIED, measured on several sessions)

```
00 01 08 01            marker, 4 bytes, constant
u32 LE                 counter, +1 per message on the stream (96.4% of gaps in the teleport ledger)
01 01 01 00            four bytes; observed also as 04 01 01 00, so it is part of the message
u16 BE                 body length
body                   body length bytes
varint                 prefix-coded trailer (see 2.1) - 1..3 bytes in practice
```

The reassembled IN channel-1 stream closes on 3602 of 4118 consecutive pairs (87.5%) in the
Test-teleport ledger; 4114 of its 4119 marker occurrences are consecutive messages. The 22.6 MB
session of 2026-09-09 does not frame with this layout at all (36% of its markers are occurrences
inside bodies), so the grammar is not identical across sessions - do not assume it.

### 1.2 Record (VERIFIED live against ledger bytes)

```
V1        varint, reader 0x6af2134     value-envelope tag
0x01      constant, not read by any hooked reader
V2        varint, reader 0x6af237f     value-envelope tag
TYPE      varint, reader 0x61ad00f     type reference; 0x0b = typeIndex 11 = ALCReplicatedState
GROUP MASK 1 byte,   reader 0x2a4371a   via bounded copy n=1; bit 0 = group 0, bit 1 = group 1
PAYLOAD    per-group field masks and fields (see 2.4)
```

Example from a live capture (frame #1370, 256 bytes): tag 16 at `+5`, type-ref at `+6` (11), group mask at
`+7`, grouped payload, then the next record at `+56`/`+57`, and so on for 11 records.

### 1.3 Type reference (VERIFIED 11,858 / 11,858 in a live run)

`FUN_1461acfe0` reads a prefix-coded varint and then either 16 raw bytes (when the value is 0) or
`table[value]`, a 16-byte entry of a table held behind `FUN_146162150()` (base at `+0x40`, end at
`+0x48`). Hooking the function and comparing its 16-byte output with the live registry gives an
exact match for every sample: `table[i]` is the uuid of the registry entry whose `typeIndex == i`.

Registry entry layout (VERIFIED by reading 3487 of them in the live process):

```
+0x00 vtable (NewWorld+0x84cb580)
+0x18 16 uuid bytes
+0x28 name storage (inline when length <= 15)
+0x38 u32 name length
+0x48 handler object pointer
+0x50 u32 index      (dense 0..3486)
+0x54 u32 typeIndex  (sparse 0..7051)
```

Notes that save time later:

- The registry carries a **name for only 312 of its 3487 entries**; for the rest the name field is
  empty in this build too. `ALCReplicatedState` is one of the unnamed ones.
- The **handler object carries the type name in UTF-16** (inline in qwords 6..9 or as a pointer in
  qword 6). Reading it gives `typeIndex 335 -> "RegistrationResponseMsg"`, `6484 ->
  "BaseGameChatMessage"`. The community dump maps those names to different slots, so its name
  column is misaligned; the handler's own name is intrinsic to the entry.
- `ALCReplicatedState` = **typeIndex 11**, registry index 1075, uuid
  `01B0664B-3AB6-44A6-87E3-8C69D40E0365`. Its name exists only in a static descriptor:
  VA `0x1480febc0` holds a pointer to the string `ALCReplicatedState` (VA `0x1480fed90`) and
  `+0xa8` holds that uuid as ASCII.

---

## 2. Readers and framing

### 2.1 Byte primitives (VERIFIED, decompiled)

| address | primitive |
|---|---|
| `0x87a190` | u8, one raw byte with an end check |
| `0x87a1c0` | u16, then a transform that is an import thunk (`jmp [IAT]`), i.e. network -> host order |
| `0x87a220` | u32, same shape |
| `0x87ad90` | u64, same shape |
| `0x87a3d0`, `0x87a330` | varint length (bound `0x2ffff`) then that many raw bytes: a length-prefixed blob |
| `0x878610` | bounded raw copy of n bytes; context `+0x08` end, `+0x10` cursor, hard end check |
| `0x87b5c0` | prefix-coded varint: 1 byte `0xxxxxxx`, 2 `10xxxxxx`, 3 `110xxxxx`, 4 `1110xxxx`, 5 `11110xxx`; payload bits 7/6/5/4/3. This is NOT the 7-bit continuation form. |
| `0x87b770` | network-order prefix varint, 1 byte up to 9 bytes, used for the field bitmask |
| `0x873220` | reader cursor getter (`*(ctx+8) - *(ctx+0x10)`), used to measure consumed bytes |
| `0x61acfe0` | type/uuid reference, see 1.3 |
| `0x6a6ddb0` | vector of u16: varint count (rejects > 100) then elements |
| `0x6ae44f0` | delta-map entry: varint value plus the byte count it consumed |
| `0x6af20d0` | value envelope: varint, consumed-size measurement, builds a 24-byte record |

**There is no float32 reader anywhere in this path (VERIFIED).** Replicated numeric values arrive
as integers with an order transform, as varints, or inside blobs. This is why byte-pattern hunts
for "plausible floats" in bodies were the wrong tool, and it is still true.

### 2.2 ALC field framing (VERIFIED, `FUN_142a436b0`)

```
group mask     1 byte
per set group: field bitmask varint (0x87b770), the dispatcher clips it with `& 0x3fffffffffffff`
per set bit n:   the n-th 16-byte entry of that group's entry vector, read through
                 `descriptor + 0x30` (the runtime vector order is measured in 2.4)
```

Two groups, group stride `0x3b0`. `FUN_142a436b0` is itself registered as a descriptor reader
(`0x1480ff960 -> 0x142a436b0`), i.e. it is the "scope" reader that wraps the per-group field sets.

### 2.3 Reader catalogue (VERIFIED: address, semantics, wire width)

| reader | wire | note |
|---|---|---|
| `0x142a42d40` | 1 B | u8 |
| `0x142a42da0` | 1 B | u8 shifted into the high half of a u16 (`<< 8`) |
| `0x142a42e10` | 2 B | u16 |
| `0x142a42e60` | 1..5 B | prefix varint |
| `0x142a42eb0` | 1 B | u8 -> float `(v << 2) / 255 - 2.0` |
| `0x142a42f30` | 4 B | u32 |
| `0x142a42f80` | 2 B | half float |
| `0x142a42fd0` | 12 B | 12 x u8 |
| `0x142a43020` | 1 B + optional | bool then an optional field |
| `0x142a43140` | varint count <= 33 + N | vector of u8 |
| `0x142a43230` | varint count <= 177 + N | vector of u8 |
| `0x142a43330` | **3 B** | **`worldPosRel`**: three quantised deltas, `0xff` = no update |
| `0x142a433d0` | **10 B** | **`worldPosAbs`**: two byte-swapped float32 + one quantised u16 |
| `0x142a434b0`, `0x142a43380` | 1 control byte + 0..3 B | quaternion |
| `0x142a43500` | 8 B | u64 |
| `0x14279e210`, `0x1417b3c60` | 1 B | u8 |
| `0x142a436b0` | nested | the field framing of 2.2 |

Descriptor base -> reader (`reader = qword at descriptor + 0x30`), from the file:

```
0x1480ff0f0 0x142a43330   0x1480ff558 0x142a42f80   0x1480ff890 0x142a43020
0x1480ff160 0x142a42f30   0x1480ff5c8 0x142a42e60   0x1480b9980 0x14279e210
0x1480ff2a0 0x142a42da0   0x1480ff730 0x142a42fd0   0x1480f46a0 0x1417b3c60
0x1480ff310 0x142a42d40   0x1480ff7a0 0x142a43230   0x1480ff960 0x142a436b0
0x1480ff398 0x142a43500   0x1480ff820 0x142a43140
0x1480ff408 0x142a433d0   0x1480ff890 0x142a43020
0x1480ff478 0x142a434b0
0x1480ff4e8 0x142a43380
```

### 2.4 Record payload: group mask, then per-group fields (VERIFIED)

A type-11 record payload is:

```
groupMask byte
for group in 0, 1, when groupMask bit group is set:
    field-mask varint
    one field per set bit in that group's entry vector
```

The byte previously called the record `flag` is the ALC **group mask**: bit 0
means group 0 is present and bit 1 means group 1 is present.  It is therefore
1 or 3 in the traced records.  A group-3 payload has two field-mask varints;
the second mask is not field data belonging to group 0.

This correction is supported by the `alcact` trace and its ledger:

- In 12,360 of the 12,388 traced outer masks, the first field reader starts at
  the mask reader's `cursor_out`; the mask is the first byte of the payload.
- The mask hook matched all 20,013 of 20,013 raw-byte/value pairs.
- In the 74-byte body at capture offset 2442, the four group-0 sections are
  `ef000140` -> 13 bytes, `e3000040` -> 7 bytes, `f300008002` -> 9 bytes,
  and `fb0003008510` -> 24 bytes.  Together with the record headers and group
  bytes they consume the body exactly.  The last section only fits when bit 38
  uses the traced 1-byte `u8State` reader, not the half-float in the old table.

The mask varint (`FUN_14087b770`) keeps the value's low bits in the first byte;
the number of leading one bits is the count of extra bytes, and the extra bytes
are little-endian.  The verified branches are:

```
value = (extra_le << max(8 - n, 0)) | first_payload, n = total bytes
n=1..5: first_payload = first & (0x7f >> (n - 1))
n=6:   first_payload = first & 0x03
n=7:   first_payload = first & 0x01
n=8..9: first_payload = 0
```

For example, `e3 00 00 40` is `0x04000003` (bits 0, 1, 26),
`f3 80 00 80 03` is `0x1c000403` (bits 0, 1, 10, 26, 27, 28), and
`fe 03 1c 00 be 7f ff 26` is `0x26ff7fbe001c03`.  The dispatcher then clips
the result with `0x3fffffffffffff` before indexing the vector.

The runtime group-0 reader sequence recovered from the same events is shown
below.  Parenthesized widths are `consumed` byte counts observed for those
samples; a slash means the reader is data-dependent.  These are reader-vector
indices, not the global property-name order in section 3.2.

```
0 u8(1)  1 u8(1)  2 u8Float(1)  3 halfFloat(2)
4 u8Float(1)  5 halfFloat(2)  6 u8Float(1)  7 halfFloat(2)
8 halfFloat(2)  9 halfFloat(2)
10 worldPosRel(3)  11 rotationQuaternion(2)  12 lookDirQuaternion(1/2/3)
13 prefixVarint(1)  14 u16(2)  15 prefixVarint(2)  16 prefixVarint(1)
17 u16(2)  18 prefixVarint(1/2)  19 prefixVarint(1)  20 u16(2)
21 prefixVarint(1/2)
25 u8High(1)  26 u8High(1)  27 worldPosAbs(10)  28 u8State(1)
29 bytes33(1)  33 bytes177(8)  34 bytes12(12)  35 u32(4)
36 halfFloat(2)  37 halfFloat(2)  38 u8State(1)
40 u64(8)  41 u8State(1)  42 u8State(1)  43 u8State(1)
44 u8State(1)  45 u8State(1)  46 prefixVarint(5)  47 u8State(1)
48 prefixVarint(1)  49 u8State(1)  50 u8State(1)  53 u32(4)
```

The trace observed only group-1 mask `01`, whose bit 0 uses a 1-byte
`u8State` reader.  It does not establish the rest of group 1.  Bits not listed
above were not set in the outer masks used for this reader-map measurement;
the decoder keeps the static family widths for those slots only as a parsing
fallback, not as group-membership evidence.

The consumed widths specifically disagree with section 3.2 at bits 8, 35--38,
40, 42, 46--48, and 53.  Bit 9 has the same 2-byte width but a different
reader position.  Bits 29 and 33 retain the section's count-plus-bytes form;
the trace samples consumed 1 byte (count zero) and 8 bytes (count seven).
The variable quaternion and prefix readers likewise show only the sample widths
above, not a new fixed-width rule.

A payload from the walking test, 22 bytes and consumed exactly, carrying the
same position the probe traced at that moment, is the group-0 portion after its
`groupMask` byte:

```
f3 80 00 80 03                     mask -> bits 0, 1, 10, 26, 27, 28
4b                                 idRel
1c                                 timeOffsetRel
ff ff ff                           worldPosRel (0xff = no delta update for this component)
52                                 timeOffsetAbs
46 0a b4 d2 45 43 69 63 28 0c      worldPosAbs = east 8877.205, north 3126.587, elevation 72.079
64                                 scopeTimeBlob0Data0
```

Quaternion fields (`FUN_14087a8d0`) are one control byte followed by the absent
components, at most three bytes.  The decoder is
`Tools/nw_capture/experimental/offline/decode_alc_state.py`; its checks are in
`test_decode_alc_state.py`.

---

## 3. The ALC type

`FUN_142a3b050` is the type factory: it resolves the allocator by name
(`"ALCReplicatedStateAllocator"`, VA `0x1480ffa68`), allocates the type object with the type name
`"ALCReplicatedState"` (VA `0x1480fed90`, allocation size `0x1560`) and calls the schema builder
`FUN_142a35db0` (`0x142a35db0`, `0x1328` bytes), which registers the ordered property list.

### 3.1 Property names, in registration order (VERIFIED, `.rdata` 0x1480ffa84..0x1480ffe40)

```
idRel                    timeOffsetRel            slayerSeqTimeRel         slayerSeqTimeAbs
worldPosRel              rotation                 lookDir                  slayerStateId
slayerStateIdStarted     slayerSequenceId         idAbs                    timeOffsetAbs
worldPosAbs              scopeTimeBlob0Data0      scopeTimeBlobEx          scopeTimeBlob1Data0
teleportAndMigrationId   scopeData                scopeInfoBlob            globalFragTags
distGround               waterDepth               aiAngleToDesiredFacing   wpnaccrystance
wpnaccrymvmnt            scopeTimeBlob0Data1      scopeTimeBlob1Data1      timeAnchor
dataBits                 moreDataBits             combinedExtraNetworkData segmentedStamina
scopelessInfoBlob        scopelessTimeBlob        hitCharacterCounter      hitStructureCounter
hitWorldCounter          gritBrokenCounter        shapeCastFilter          slayerScriptLayers
slayerScriptFlags        forbiddenBounds          currentGridAccessibility scopeTimeBlob0Data2
scopeTimeBlob0Data3      scopeTimeBlob1Data2      scopeTimeBlob1Data3      quantization
```

48 names. The next unrelated type in `.rdata` is `CAGEDataAllocator`.

### 3.2 The 63-bit field table (VERIFIED: bit, field, member offset, reader, wire width)

This is the static schema builder's registration order. `FUN_142a35db0` writes each field's codec
block (descriptor pointer at the block, reader at `descriptor+0x30`) and then pushes one 16-byte
`(name, block)` entry per bit. It is useful for member offsets and the static reader catalogue, but
it is not the runtime group-0 entry order measured in 2.4; do not use this table alone to consume a
record payload.

| bit | field | member | reader | wire |
|---:|---|---:|---|---|
| 0 | `idRel` | `+0x7d8` | `0x142a42d40` | 1 B |
| 1 | `timeOffsetRel` | `+0x858` | `0x142a42d40` | 1 B |
| 2 | `slayerSeqTimeRel` | `+0xcb0` | `0x142a42eb0` | 1 B (u8 -> float [-2,2]) |
| 3 | `slayerSeqTimeAbs` | `+0xc88` | `0x142a42f80` | 2 B (half float) |
| 4 | `slayerSeqTimeRel` | `+0xd08` | `0x142a42eb0` | 1 B |
| 5 | `slayerSeqTimeAbs` | `+0xce0` | `0x142a42f80` | 2 B |
| 6 | `slayerSeqTimeRel` | `+0xd60` | `0x142a42eb0` | 1 B |
| 7 | `slayerSeqTimeAbs` | `+0xd38` | `0x142a42f80` | 2 B |
| 8 | `slayerSeqTimeRel` | `+0xdb8` | `0x142a42eb0` | 1 B |
| 9 | `slayerSeqTimeAbs` | `+0xd90` | `0x142a42f80` | 2 B |
| 10 | **`worldPosRel`** | **`+0x910`** | **`0x142a43330`** | **3 B** |
| 11 | `rotation` | `+0x9b0` | `0x142a43380` | 1 + 0..3 B (quaternion) |
| 12 | `lookDir` | `+0x960` | `0x142a434b0` | 1 + 0..3 B (quaternion) |
| 13 | `slayerStateId` | `+0xac0` | `0x142a42e60` | 1..5 B (prefix varint) |
| 14 | `slayerStateIdStarted` | `+0xb60` | `0x142a42e10` | 2 B (u16) |
| 15 | `slayerSequenceId` | `+0xbe0` | `0x142a42e60` | 1..5 B |
| 16 | `slayerStateId` | `+0xae8` | `0x142a42e60` | 1..5 B |
| 17 | `slayerStateIdStarted` | `+0xb80` | `0x142a42e10` | 2 B |
| 18 | `slayerSequenceId` | `+0xc08` | `0x142a42e60` | 1..5 B |
| 19 | `slayerStateId` | `+0xb10` | `0x142a42e60` | 1..5 B |
| 20 | `slayerStateIdStarted` | `+0xba0` | `0x142a42e10` | 2 B |
| 21 | `slayerSequenceId` | `+0xc30` | `0x142a42e60` | 1..5 B |
| 22 | `slayerStateId` | `+0xb38` | `0x142a42e60` | 1..5 B |
| 23 | `slayerStateIdStarted` | `+0xbc0` | `0x142a42e10` | 2 B |
| 24 | `slayerSequenceId` | `+0xc58` | `0x142a42e60` | 1..5 B |
| 25 | `idAbs` | `+0x7b8` | `0x142a42da0` | 1 B (high byte of a u16) |
| 26 | `timeOffsetAbs` | `+0x838` | `0x142a42da0` | 1 B |
| 27 | **`worldPosAbs`** | **`+0x8c0`** | **`0x142a433d0`** | **10 B** |
| 28 | `scopeTimeBlob0Data0` | `+0x10c0` | `0x14279e210` | 1 B |
| 29 | `scopeTimeBlobEx` | `+0x11c8` | `0x142a43140` | varint <= 33 + N |
| 30 | `scopeTimeBlob1Data0` | `+0x1148` | `0x14279e210` | 1 B |
| 31 | `teleportAndMigrationId` | `+0xe38` | `0x14279e210` | 1 B |
| 32 | `scopeData` | `+0xed8` | `0x142a42e60` | 1..5 B |
| 33 | `scopeInfoBlob` | `+0xf20` | `0x142a43230` | varint <= 177 + N |
| 34 | `globalFragTags` | `+0xde0` | `0x142a42fd0` | 12 B |
| 35 | `distGround` | `+0x1508` | `0x14279e210` | 1 B |
| 36 | `waterDepth` | `+0x1528` | `0x14279e210` | 1 B |
| 37 | `aiAngleToDesiredFacing` | `+0xa00` | `0x142a42f30` | 4 B (u32) |
| 38 | `wpnaccrystance` | `+0xa28` | `0x142a42f80` | 2 B (half float) |
| 39 | `wpnaccrymvmnt` | `+0xa50` | `0x142a42f80` | 2 B (half float) |
| 40 | `scopeTimeBlob0Data1` | `+0x10e0` | `0x14279e210` | 1 B |
| 41 | `scopeTimeBlob1Data1` | `+0x1168` | `0x14279e210` | 1 B |
| 42 | `timeAnchor` | `+0x7f8` | `0x142a43500` | 8 B (u64) |
| 43 | `dataBits` | `+0x878` | `0x14279e210` | 1 B |
| 44 | `moreDataBits` | `+0x898` | `0x14279e210` | 1 B |
| 45 | `combinedExtraNetworkData` | `+0x1450` | `0x14279e210` | 1 B |
| 46 | `segmentedStamina` | `+0xf00` | `0x14279e210` | 1 B |
| 47 | `scopelessInfoBlob` | `+0x1240` | `0x142a43230` | varint <= 177 + N |
| 48 | `scopelessTimeBlob` | `+0x13d8` | `0x142a43140` | varint <= 33 + N |
| 49 | `hitCharacterCounter` | `+0xe58` | `0x14279e210` | 1 B |
| 50 | `hitStructureCounter` | `+0xe78` | `0x14279e210` | 1 B |
| 51 | `hitWorldCounter` | `+0xe98` | `0x14279e210` | 1 B |
| 52 | `gritBrokenCounter` | `+0xeb8` | `0x14279e210` | 1 B |
| 53 | `shapeCastFilter` | `+0x1470` | `0x142a42e60` | 1..5 B |
| 54 | `slayerScriptLayers` | `+0xa78` | `0x14279e210` | 1 B |
| 55 | `slayerScriptFlags` | `+0xa98` | `0x142a42e60` | 1..5 B |
| 56 | `forbiddenBounds` | `+0x1498` | `0x142a43020` | 1 B + optional |
| 57 | `currentGridAccessibility` | `+0x14e8` | `0x1417b3c60` | 1 B |
| 58 | `scopeTimeBlob0Data2` | `+0x1100` | `0x14279e210` | 1 B |
| 59 | `scopeTimeBlob0Data3` | `+0x1120` | `0x14279e210` | 1 B |
| 60 | `scopeTimeBlob1Data2` | `+0x1188` | `0x14279e210` | 1 B |
| 61 | `scopeTimeBlob1Data3` | `+0x11a8` | `0x14279e210` | 1 B |
| 62 | `quantization` | `+0x938` | `0x142a42f30` | 4 B (u32) |

Vector families, in case a single row is not enough: `slayerStateId`, `slayerSequenceId` and
`slayerStateIdStarted` are vectors of 4 elements (`+0xac0`, `+0xbe0`, `+0xb60`), and
`slayerSeqTimeRel`/`slayerSeqTimeAbs` is a vector of 4 elements of `0x58` bytes at `+0xc80`; the bits
offered above interleave those elements by index. `scopeTimeBlob0Data0..3` and
`scopeTimeBlob1Data0..3` are the four u8 elements inside the `0x88`-byte scopeTimeBlob elements.
The per-element codec comes from the element initialisers (`FUN_142a38ed0` for the varint families,
`FUN_142a38ea0` for `slayerStateIdStarted`, `FUN_142a35830` for the `0x58` elements, `FUN_142a38e70`
for the blob data bytes), which is why those blocks carry no static descriptor in the builder.

Corrections to what this document said earlier: `scopeTimeBlob*Data*` are **u8** (1 B), not
`varint <= 33` vectors - the `0x142a43140` reader belongs to `scopeTimeBlobEx` and
`scopelessTimeBlob`; `gritBrokenCounter` (`+0xeb8`) was missing; `currentGridAccessibility` reads
through `0x1417b3c60`; and `forbiddenBounds` is a bool plus an optional field, not a plain read.

Cross-check that anchored the join: `FUN_142a3cdc0` is literally `FUN_142a273b0(param_1 + 0x8c0)`,
i.e. the assembler that turns a decoded `worldPosAbs` into world coordinates.

The group model is now verified in the record payload: the byte after the type is the group mask,
and group 0 and group 1 each have their own field-mask reader.  The supplied trace establishes the
group-0 reader map listed in 2.4 and only group-1 bit 0; unobserved group-1 bits and the semantic
names of the reordered group entries remain open.

### 3.3 Position encoding (VERIFIED mechanics, decoded on real data)

`worldPosAbs` (10 wire bytes):

```
float32 BE   x            (the u32 is read through the import thunk that converts network -> host)
float32 BE   z
u16 BE       quantised third component, mapped into the range [-100, 1000] (code multiplies by
             1/65535 and adds the range base) together with a per-entity scale argument
```

`worldPosRel` (3 wire bytes): three deltas, `delta = quantization * (2b/255 - 1)` with `quantization`
coming from the `quantization` field; the byte `0xff` means "no update" for that component - this is
the `worldPosRel [255,255,255]` sentinel the community describes.

Measured on a walking test (two 4 s walks with 12 s stops, character driven by the repo's virtual
keyboard tooling while tracing only these two readers):

```
track 1 (the local player): 378 samples
  x  8786.66 -> 8893.83   z  3003.97 -> 3126.63   y  58.03 -> 74.35
  x steps between updates: 2.014, 2.081, 2.022, 2.07, 2.139, 2.128, 2.072, 2.07, ...
```

`x` advances monotonically by about 2 units per update while walking, `z` drifts slowly and `y`
stays inside a 16 unit band. The same track is flat before and after the walks.

Second component check: with the u16 read big-endian a standing entity reports a stable value
(`10259 -> y 72.20`, `10252 -> y 72.08`); little-endian oscillates between -95 and 992, so
big-endian is the correct order (VERIFIED by that measurement, not by the naming).

INFERRED, do not treat as fact:

- ~~which of the two floats is the north-south axis~~ resolved, see 3.4 (first float = east, second = north);
- the exact affine mapping of the quantised component: the `[-100, 1000]` and `1/65535` constants
  are read in the code, the pairing with the per-entity scale argument was not;
- ~~the per-field bit order inside the two field bitmasks of 2.2~~ resolved for the supplied trace:
  the runtime group-0 vector is enumerated in 2.4; group-1 entries remain unobserved beyond bit 0.

### 3.4 Placement on the community maps (VERIFIED)

Two label sets, do not mix them: this document names the first float `x` (east), the second float `z`
(north) and the quantised u16 `y` (**height**). The community maps name the same three values `X` =
first float (east), `Y` = second float (north), `Z` = the quantised u16. So this document's `z` is the
map's `Y`, and this document's `y` is the map's `Z`.

- `aeternum-map.th.gl` consumes the game numbers unscaled and plots the player at leaflet `[Y, X]`
  (`PositionContext.tsx` -> `[location.y, location.x]`; live bundle `MarkersContext-*.js` ->
  `Transformation(1/16, 0, -1/16, 0)` with `setView([i.y, i.x], zoom)`).
- Independent check against `https://aeternum-map.th.gl/api/markers` (55739 markers, 3621 with a
  non-zero elevation) over the 136 unique decoded positions: correct assignment gives a median of
  16.6 units to the nearest marker and a median elevation error of 1.38, the swapped assignment
  781 units. A second run over only the 48 walk samples gave 34.3 / 2.25 against 2642 / 66.35.
- Region of the walking test: **Windsward**, along the Elin River valley. Nearest named markers to
  the track centre (8800, 3060): `Bastion Windsward` 262, `North Windsward Watch` 278,
  `Scenic Painting of the Elin River` 297, `Amrine Excavation` 529, nearest settlement `Corinth` 643.
- Deep link, all three parameters mandatory: `https://aeternum-map.th.gl/?x=<X>&y=<Y>&zoom=<z>`
  (also `?bounds=west,south,east,north`). `metaforge.app/new-world/map/#/?lng=<X>&lat=<Y>&zoom=<z>`
  responds, but its `lat` passes through a minified transform that was not resolved. `nwdb.info/map`
  and `newworldminimap.com/map` have no coordinate deep link; their `x`/`y`/`z` are tile indices.
- "1 unit = 1 metre" is community usage, not verified in any source read.
- The tiles cannot be overlaid from a plain HTML page any more (the repo tile URLs return the SPA
  shell), but drawing into the live page works: `Tools/nw_capture/experimental/nw_map_trail.js`.

Full report and citations: [nwdb-map-research.md](nwdb-map-research.md).

---

## 4. Instrumentation playbook

Attach (documented route, no game restart, no focus needed for capture):

```sh
# one-shot capture with any probe, against the already-running game
.venv-capture/bin/python Tools/nw_capture/experimental/nw_capture_probe.py \
    --probe "$PWD/Tools/nw_capture/experimental/nw_pos_probe.js" --seconds 60 --label pos
# drive the character while capturing (needs the game focused; the tool guards and restores focus)
.venv-capture/bin/python Tools/nw_capture/experimental/nw_walktest.py \
    --seq "w:4,release:12,w:4,release:12" --wait-focus 120
```

It starts `frida-server.exe` inside the existing Proton prefix
(`SteamLinuxRuntime_4/run -- "Proton 11.0/files/bin/wine" Tools/nw_capture/frida-server.exe
--listen 127.0.0.1:27943`, `WINEPREFIX=.../compatdata/1063730/pfx`), attaches through the remote
device, loads the repo's ledger hooks plus the probe, and leaves the game running.

Correlation rules that cost real time to learn:

- `_runner.py` resolves probe paths against `Tools/nw_capture/`, so pass absolute paths.
- Hooking `0x87b5c0` and reading `ctx+0x10` **on leave** gives the cursor *after* the varint, so the
  value's first byte is at `offset - size`. Hooking `0x878610` and reading the cursor **on enter**
  gives the exact position of that read.
- Matching events to a captured ledger by a 16-byte window is ambiguous; require a unique 40-byte
  window, or correlate by monotone cursor chains per buffer.
- Background jobs need `setsid`, otherwise they die when the invoking shell exits and the capture
  silently covers only part of the test.
- Long-running assumptions are cheap to check: a 5 s capture showed 0 samples from the very readers
  that delivered 378 samples once the test was set up correctly.

Driving the game from the outside:

- **Keyboard/mouse injection goes to the focused window** and can leak into the operator's terminal:
  `nw_vkeys.py` refuses to inject unless the expected window class is focused, re-checks before each
  step, and releases everything on abort.
- **A virtual gamepad does not work unattended**: SDL ignores joystick events when the window is not
  focused (background-events hint is off by default), and Wine did not pick the uinput pad up at all
  in this setup. The pad tool is kept for completeness, not for tests.
- Focus control on Hyprland 0.56 is Lua: `hyprctl dispatch 'hl.dsp.focus({window="class:steam_app_1063730"})'`.
  The legacy `focuswindow class:...` form fails with a parse error.

---

## 5. Tools in this repo

| tool | purpose |
|---|---|
| `decode_position.py` | pos_samples log -> decoded positions (JSON, CSV) + per-entity track summary |
| `nw_pos_probe.js` | traces exactly the two position readers (`0x142a433d0`, `0x142a43330`) |
| `nw_field_probe.js` | traces the candidate field readers with values for co-movement checks |
| `nw_capture_probe.py` | attach + capture with any probe, writes ledger and JSONL log |
| `nw_vkeys.py` / `.sh` | hold keys in the focused game, focus guard, focus restore |
| `nw_walktest.py` / `.sh` | capture plus driven keys in one run |
| `nw_vpad.py` / `.sh` | virtual gamepad (see the SDL focus caveat above) |
| `decode_in_bodies.py` | frame cutting and body-to-record split, with measured rates |
| `decode_wire_type_ids.py` | type reference values -> registry entries and names |
| `decode_alc_state.py` | record payload -> the 63 ALC fields with values (see 2.4); `test_decode_alc_state.py` checks it |
| `probe_framing.py`, `probe_type_ids.py`, `probe_registry_static.py`, `probe_position_hunt.py`, `probe_position_candidates.py` | offline probes kept from earlier steps |
| `ghidra/Sweep.java` | headless Ghidra script: disassemble a window, create the function, decompile |

Ghidra setup in use: Ghidra 12.1.3 with JDK 21 (`ghidra-headless` wrapper), project
`~/ghidra-projects/nw`, program `NewWorld.exe` imported **without** auto-analysis; `VA = 0x140000000
+ RVA`. Ghidra refuses project paths containing dot-directories. Its `.text` block has holes inside
its nominal span, so a wrong address looks like "no code" instead of an error - check the file bytes
before concluding anything.

---

## 6. Dead ends, so nobody repeats them

- **Byte-pattern hunts for coordinates.** Plausible-looking float32 pairs appear in bodies
  (`(15290.3, 4442.3)`), and 123 candidate slots were tracked across a teleport capture: zero showed
  the stable-jump-stable signature. They were coincidences. The reader's identity, not the value's
  plausibility, is what makes a field a position.
- **The community's `0x970C0A5D` "Message V3 signature".** It appears zero times in our ledger
  streams and zero times as a code immediate; the marker our decoder uses is not in code either
  (4 occurrences in `.rdata`, no pointer references). Only structure identifies it.
- **The AZ read driver `0x146160ae0`** is never called during normal play (hooked for 60 s, zero
  calls), so inbound replication does not go through the AZ `SerializeContext` reader path.
- **`.rdata` around `0x148552230`** is CryEngine/renderer data plus unrelated reflection clusters
  (`LoadoutItems...`), not ALC.
- **The community registry dump's name column is misaligned** relative to the index/typeIndex it
  carries; do not use it to label slots.
- **The 22.6 MB session of 2026-09-09** does not share the frame grammar: 36% of its markers are
  inside bodies.

## 7. Open questions worth a targeted look later

1. ~~The per-field bit order inside the ALC field bitmasks~~ RESOLVED for the static schema: the
   table in 3.2 is the registration order. Runtime record payloads additionally have a group mask
   and separate group vectors (2.4), whose group-0 order is measured only where the trace set a bit;
   group-1 bit 0 is the only group-1 entry observed.
2. ~~Readers and offsets for the ~14 unrecovered fields~~ RESOLVED: all 63 fields now have an offset,
   a reader and a wire width (3.2); the per-element codecs of the vector families come from the
   element initialisers listed there.
3. ~~Which float is the north-south axis, and the mapping to the Aeternum map~~ RESOLVED, see 3.4: the
   axis assignment is verified against the marker set and the community maps consume the game
   coordinates unscaled.
4. The `scopeTimeBlob*` and `scopeInfoBlob` payload semantics (varint-counted byte vectors).
5. Whether the `0x142a3b050` factory has sibling factories for the other 3476 registry entries, which
   would give the same reference material for every other type.
6. ~~The high-bit packing of the mask varint `FUN_14087b770`~~ RESOLVED: the `0xf8`..`0xff`
   branches use 6..9 total bytes, with little-endian extra bytes and zero, one, or two payload bits
   in the first byte as described in 2.4.  The 20,013/20,013 raw-byte/value matches and the 74-byte
   ledger body verify the implementation, including bit 33 and the high-bit reader widths. The
   remaining group-1 membership question is recorded in 2.4.
