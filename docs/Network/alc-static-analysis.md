# ALCReplicatedState (registry typeIndex 11): static field readers and wire layout

Author: agent A (static, Ghidra 12.1.3 + python on the file bytes)
Target: `~/ghidra-projects/nw` / program `NewWorld.exe`, image base 0x140000000, NO auto-analysis.
All VAs below are absolute (VA = 0x140000000 + RVA) unless noted. Method: PE section
map + `.pdata` RUNTIME_FUNCTION table (parsed in python) to get exact function
boundaries, then `Sweep.java` (linear disassemble + decompile) on the exact function
ranges, plus a python abstract-execution pass over the raw listing of the ALC
registration function to recover the name -> member-offset table.

Raw evidence (all under /tmp/nwc/): A-run1.log..A-run10.log (Ghidra), A-pdata.log,
A-alc-region.log, A-xrefs2.log, A-callers.log, A-callers2.log, A-primcallers.log,
A-alcmap.log, A-names2.log, A-join.log, A-consts.log, A-funcs.txt.

Convention in this file: **VERIFIED** = read in the code/bytes (address + quoted line),
**INFERRED** = conclusion that goes beyond what the code literally states.

---

## 0. Identity of the type (VERIFIED)

`FUN_142a3b050` (0x142a3b050, 0x12e bytes) is the type factory / registration entry for
ALC. It resolves the allocator by name and then allocates the type object with the type
name string, then builds the property schema:

```c
uVar3 = func_0x0001413f94b0(&UNK_1480ffa68);         // "ALCReplicatedStateAllocator"
...
puVar2 = (undefined8 *)
         (**(code **)(*(longlong *)(_DAT_14a33d3d8 + 0x30) + 8))
                   ((longlong *)(_DAT_14a33d3d8 + 0x30),0x1560,0x10,0,&UNK_1480fed90,0,0,0,uVar3);
*(undefined4 *)(puVar2 + 1) = 1;
*(undefined4 *)((longlong)puVar2 + 0xc) = 1;
*puVar2 = &UNK_148100338;
puStack_38 = puVar2;
FUN_142a35db0(puVar2 + 2);                            // <- ALC property/schema builder
*param_2 = puVar2 + 2;
param_2[1] = puVar2;
```

* `0x1480fed90` = ASCII `"ALCReplicatedState"` (the type name passed to the allocator).
* `0x1480ffa68` = ASCII `"ALCReplicatedStateAllocator"`.
* allocation size `0x1560`, name string `"ALCReplicatedState"`.
* VERIFIED: `FUN_142a3b050` is reached from the ALC slot tables only through
  `[0x1480ff9b8] = 0x142a3b050` and `ptr_refs` shows exactly two references to the type
  name string: `0x142a3b11a` (inside `FUN_142a3b050`) and `0x142a3c273`
  (a leaf, not decompiled in budget).

`FUN_142a35db0` (0x142a35db0..0x142a370d8, 0x1328 bytes) is the schema builder. It is
called from the ALC slot wrappers `FUN_142a327f0` (0x142a32808), `FUN_142a32890`
(0x142a328db), from `FUN_142a3b050` (0x142a3b15b) and from `0x144882cce`
(caller `FUN_144882c70`).

---

## 1. The `.rdata` region around 0x148552230 and the region that matters (task step 1)

### 1a. 0x148552230 +/- 0x40000 is NOT serialization code
Scan of 0x148512230..0x148592230 (python over the file, log A-rdata-scan.log) shows
CryEngine/renderer strings (`D3D Detected: AMD video card`, `q_ShaderGeneral`,
`SPoolManager::Initialize`, ...) plus CryEngine vtables. The only interesting hit is
`0x1485521d0 "m_linkedLoadoutItems"/"m_isForGameMode"`-style property-name clusters
(LoadoutItems…), i.e. unrelated class descriptors. **Conclusion: the ALC reader is not in
this region; the task's hint about "LoadoutItems then pointers" points at a generic
reflection cluster, not ALC.**

### 1b. Where ALC actually lives (VERIFIED)
The ALC type name and the *ordered property-name list* are next to each other in
`.rdata`, immediately after a table of code pointers:

```
VA            bytes (string) / pointer
0x1480fed90   "ALCReplicatedState"
0x1480ff9d0   qword 0x140872230       ) code-pointer table (readers/descriptor helpers)
0x1480ffa50   qword 0x142a3c270       ) leaf that lea's "ALCReplicatedState"
0x1480ffa68   "ALCReplicatedStateAllocator"
0x1480ffa84   "idRel"
0x1480ffa90   "timeOffsetRel"
0x1480ffaa0   "slayerSeqTimeRel"
0x1480ffab8   "slayerSeqTimeAbs"
0x1480ffad0   "worldPosRel"
0x1480ffae0   "rotation"
0x1480ffaf0   "lookDir"
0x1480ffaf8   "slayerStateId"
0x1480ffb08   "slayerStateIdStarted"
0x1480ffb20   "slayerSequenceId"
0x1480ffb34   "idAbs"
0x1480ffb40   "timeOffsetAbs"
0x1480ffb50   "worldPosAbs"
0x1480ffb60   "scopeTimeBlob0Data0"
0x1480ffb78   "scopeTimeBlobEx"
0x1480ffb88   "scopeTimeBlob1Data0"
0x1480ffba0   "teleportAndMigrationId"
0x1480ffbb8   "scopeData"
0x1480ffbc8   "scopeInfoBlob"
0x1480ffbd8   "globalFragTags"
0x1480ffbe8   "distGround"
0x1480ffbf8   "waterDepth"
0x1480ffc08   "aiAngleToDesiredFacing"
0x1480ffc20   "wpnaccrystance"
0x1480ffc30   "wpnaccrymvmnt"
0x1480ffc40   "scopeTimeBlob0Data1"
0x1480ffc58   "scopeTimeBlob1Data1"
0x1480ffc70   "timeAnchor"
0x1480ffc80   "dataBits"
0x1480ffc90   "moreDataBits"
0x1480ffca0   "combinedExtraNetworkData"
0x1480ffcc0   "segmentedStamina"
0x1480ffcd8   "scopelessInfoBlob"
0x1480ffcf0   "scopelessTimeBlob"
0x1480ffd08   "hitCharacterCounter"
0x1480ffd20   "hitStructureCounter"
0x1480ffd38   "hitWorldCounter"
0x1480ffd48   "gritBrokenCounter"
0x1480ffd60   "shapeCastFilter"
0x1480ffd70   "slayerScriptLayers"
0x1480ffd88   "slayerScriptFlags"
0x1480ffda0   "forbiddenBounds"
0x1480ffdb0   "currentGridAccessibility"
0x1480ffdd0   "scopeTimeBlob0Data2"
0x1480ffde8   "scopeTimeBlob0Data3"
0x1480ffe00   "scopeTimeBlob1Data2"
0x1480ffe18   "scopeTimeBlob1Data3"
0x1480ffe30   "quantization"
0x1480ffe40   "CAGEDataAllocator"     (next unrelated type follows)
```

### 1c. Static property-type descriptor blocks (VERIFIED structure)
Scattered through `.rdata` 0x1480ff0f0..0x1480ff990 there are static descriptor objects
used as *property types* by the ALC schema. For every one of them the **field reader is
the code pointer at descriptor + 0x30**:

```
descriptor   reader(at +0x30)   descriptor  reader
0x1480ff0f0  0x142a43330        0x1480ff558  0x142a42f80
0x1480ff160  0x142a42f30        0x1480ff5c8  0x142a42e60
0x1480ff2a0  0x142a42da0        0x1480ff730  0x142a42fd0
0x1480ff310  0x142a42d40        0x1480ff7a0  0x142a43230
0x1480ff398  0x142a43500        0x1480ff820  0x142a43140
0x1480ff408  0x142a433d0        0x1480ff890  0x142a43020
0x1480ff478  0x142a434b0        0x1480b9980  0x14279e210
0x1480ff4e8  0x142a43380        0x1480f46a0  0x1417b3c60
0x1480ff730  0x142a42fd0        0x1480ff960  0x142a436b0
```
(the table above is the join of: descriptor addresses written by `FUN_142a35db0`, and
qword(descriptor+0x30) read out of the file; see A-join.log.)

The block bases are not equally spaced (0x70, 0x88, ... stride) because each block also
embeds the type's own type-identity data. What is uniform and verified: **reader =
qword at block+0x30**, and the dispatcher calls it as a *virtual method*:
`(**(code **)(*(longlong *)*plVar6 + 0x30))((longlong *)*plVar6,param_2)` where `*plVar6`
is the descriptor pointer held in the 16-byte vector entry.

---

## 2. The wire framing used by ALC (VERIFIED)

`FUN_142a436b0` (0x142a436b0, 0x215 bytes) is registered as a property reader itself
(`ptr_refs(0x142a436b0) = {0x1480ff260, 0x1480ff990}`, i.e. it is the reader of the
descriptor blocks based at 0x1480ff230 and 0x1480ff960). It is the canonical mask-driven
record reader, and it shows the wire shape exactly:

```c
auStackX_18[0] = 0;
uVar2 = FUN_140878610(param_2,auStackX_18,1,&uStackX_8);      // group presence mask, 1 byte
if ((char)uStackX_8 == '\0') goto LAB_142a4389d;
...
do {
  uVar2 = (ulonglong)auStackX_18[uVar7 >> 5];
  if ((auStackX_18[uVar7 >> 5] >> ((byte)uVar7 & 0x1f) & 1) != 0) {      // bit g of the mask
    lVar3 = func_0x000140873220(param_2);                                // bit cursor before
    uStackX_20 = 0;
    uVar2 = FUN_14087b770(&uStackX_8,&uStackX_10,&uStackX_20,param_2);    // field bitmask (varint)
    ...
    lStack_88 = func_0x000140873220(param_2);
    lStack_88 = lVar3 - lStack_88;                                       // bytes consumed
    puStack_78 = (undefined *)(uStackX_20 & 0x3fffffffffffff);           // mask clipped to 54 bits
    ...
    do {
      if (((ulonglong)(&puStack_78)[uVar4 >> 6] >> ((byte)uVar4 & 0x3f) & 1) != 0) {
        func_0x000140873220(param_2);
        uVar2 = (**(code **)(*(longlong *)*plVar6 + 0x30))((longlong *)*plVar6,param_2);  // FIELD READER
        if ((char)uVar2 == '\0') goto LAB_142a4389d;
      }
      uVar4 = uVar4 + 1;
      plVar6 = plVar6 + 2;                    // 2 qwords = 16-byte entry
    } while (uVar4 < uVar2);
  }
  uVar7 = uVar7 + 1;
  plVar5 = plVar5 + 0x76;                     // 0x76 qwords = 0x3b0 = next group
} while (uVar7 < 2);
```

`FUN_142a43550` (0x142a43550) is the single-group variant of the same pattern:
`lVar3 = func_0x000140873220(param_2); uVar1 = FUN_14087b770(...); ... uStack_30 = uStack_48 & 0x3fffffffffffff;`
then the identical `vtable+0x30` reader loop over `param_1[0xf2] - (param_1 + 0xee) >> 4`
16-byte entries.

**Wire framing (VERIFIED):**

```
u8  groupMask                       // FUN_140878610(...,1,...) exact 1 byte
for g in 0..1:                      // 2 groups, group state stride 0x3b0
    if groupMask bit g set:
        varint fieldMask            // FUN_14087b770 (network-order prefix varint, 1..9 bytes)
        for f in 0..53:             // mask is clipped with & 0x3fffffffffffff (54 bits)
            if fieldMask bit f set:
                <field g,f reader>  // virtual call, descriptor vtable +0x30
```
Field order inside one bitmask is the *entry order* of the group vector, which is the
order in which `FUN_142a35db0` pushed the entries (the name order below).

`func_0x000140873220` (0x140873220, leaf, no .pdata unwind entry) is the bit cursor:
```c
longlong FUN_140873220(longlong param_1) { return *(longlong *)(param_1 + 8) - *(longlong *)(param_1 + 0x10); }
```
and the dispatcher takes `before - after` to measure the consumed size of each nested
entry (this is the "measured byte count" that the old capture analysis saw).

`FUN_14087b770` (0x14087b770, 0x44 bytes window; the linear sweep over-ran into
neighbouring code in Ghidra's decompilation, but the prefix-decode ladder is readable) is
the *network-order* prefix varint (byte-reversed, prefix length coding):
```
0xxxxxxx           1 byte,  value = b                      (uVar8 = (ulonglong)bStack_18)
10xxxxxx +1        2 bytes, value = (b1 << 6) | (b0 & 0x3f)
110xxxxx +2        3 bytes, << 5
1110xxxx +3        4 bytes, << 4
11110xxx +4        5 bytes, << 3
111110xx +5        6 bytes, << 2
1111110x +6        7 bytes, << 1
11111110 +7        8 bytes, (uVar5 = uVar5 & 0xff)
11111111 +8        9 bytes, (uVar5 = uVar5 & 0xff)
```
(This is distinct from 0x14087b5c0 = the little-endian prefix varint already known.)

---

## 3. The per-field readers (VERIFIED, with byte counts)

All these are the *field readers* reached through descriptor+0x30. Each writes the decoded
value into the field record at +0x10 and sets the "has value" byte at +0x16 / +0x1c /
+0x13 / ... to 1, plus stores the global `_DAT_14a435a40` (a .data sentinel) at +0x08.

| reader | primitive used | bytes on wire | quoted line |
|---|---:|---:|---|
| `0x142a42d40` | `FUN_14087a190` (u8) | **1** | `*(ushort *)(param_1 + 0x10) = (ushort)abStackX_18[0];` |
| `0x142a42da0` | `FUN_14087a190` (u8) | **1** | `*(ushort *)(param_1 + 0x10) = (ushort)abStackX_18[0] << 8;` |
| `0x142a42e10` | `FUN_14087a1c0` (u16) | **2** | `lVar1 = FUN_14087a1c0(param_1 + 0x17,auStackX_8,param_1 + 0x10,param_2);` |
| `0x142a42e60` | `FUN_14087b5c0` (prefix varint) | **1..5** | `lVar1 = FUN_14087b5c0(param_1 + 0x1d,auStackX_8,param_1 + 0x10,param_2);` |
| `0x142a42eb0` | `FUN_14087a190` (u8) | **1** | `*(float *)(param_1 + 0x10) = (float)((uint)abStackX_18[0] << 2) * _DAT_147f40048 - _DAT_147efa334;` |
| `0x142a43500` | `FUN_14087ad90` (u64) | **8** | `lVar1 = FUN_14087ad90(param_1 + 0x29,auStackX_8,param_1 + 0x10,param_2);` |
| `0x142a42f30` | `FUN_14087a270` (u32) | **4** | `lVar1 = FUN_14087a270(param_1 + 0x1d,auStackX_8,param_1 + 0x10,param_2);` |
| `0x142a42f80` | `FUN_14087ae90` (half float) | **2** | `lVar1 = FUN_14087ae90(param_1 + 0x1d,auStackX_8,param_1 + 0x10,param_2);` |
| `0x14279e210` | `FUN_14087a190` (u8) | **1** | `lVar1 = FUN_14087a190(param_1 + 0x14,auStackX_8,param_1 + 0x10,param_2);` |
| `0x1417b3c60` | `FUN_14087a190` (u8) | **1** | `uVar2 = FUN_14087a190(param_1 + 0x14,&uStackX_18,auStackX_8,param_2);` |
| `0x142a43140` | `FUN_14087b5c0` + N x u8 | **1..5 + N (N<=33)** | `if ((cStackX_19 != '\0') && (uVar2 = (ulonglong)auStack_28[0], auStack_28[0] < 0x21)) { ... }` then `FUN_14087a190(auStackX_8,&uStackX_20,lVar4,param_2)` per element |
| `0x142a43230` | `FUN_14087b5c0` + N x u8 | **1..5 + N (N<=177)** | `... auStack_28[0] < 0xb1 ...` then `FUN_14087a190(...)` per element |
| `0x142a43020` | `FUN_140878610` (raw) + optional | **1 (+ optional block)** | `FUN_140878610(param_2,abStackX_10,1,acStackX_8); if (abStackX_10[0] < 2) { *(bool *)(param_1 + 0x24) = abStackX_10[0] != 0; ...` |
| `0x142a433d0` | 2 x `FUN_14087a270` + `FUN_14087adf0` | **10** | `FUN_14087a270(auStackX_8,&uStackX_18,&uStack_20,param_2); FUN_14087a270(auStackX_8,&uStackX_20,(longlong)&uStack_20 + 4,param_2); ... FUN_14087adf0(auStack_30,&uStack_38,auStack_18,param_2);` |
| `0x142a43330` | `FUN_1417b1da0` | **3** | see worldPosRel below |
| `0x142a434b0` | `FUN_14087afe0` | **1 + 0..3** | quaternion, below |
| `0x142a43380` | `FUN_14087b060` | **1 + 0..3** | quaternion, below |
| `0x142a42fd0` | `FUN_142a75ee0` | **12** | `do { lVar1 = FUN_14087a190(auStack_18,auStack_10,uVar2 + param_3 + 8,param_4); ... } while (uVar2 < 0xc);` |
| `0x142a436b0` | mask dispatcher | nested | see section 2 |

Supporting primitives resolved this session:

* `FUN_14087a190` u8 (1 B), `FUN_14087a1c0` u16 (2 B), `FUN_14087ad90` u64 (8 B),
  `FUN_14087b5c0` little-endian prefix varint, `FUN_140878610` raw copy n bytes: already
  known, reused.
* `FUN_14087a270` (0x14087a270): `uVar2 = **(undefined4 **)(param_4 + 0x10); ...; uVar2 = FUN_146167960(uVar2); *param_3 = uVar2;`
  one raw **u32** (4 B) followed by a byte-swap (`FUN_146167960` -> `Ordinal_14`).
* `FUN_14087acf0` (0x14087acf0): two raw **u32** with the same swap = **8 B**.
* `FUN_14087ae90` (0x14087ae90): one raw **u16** (2 B) then an IEEE **half-float**
  expansion (`0x7c00`, `0x3ff`, `0x8000` masks): `uVar4 = func_0x000146167940(uVar2); if ((uVar4 & 0x7fff) == 0) ...`
* `FUN_14087adf0` (0x14087adf0): one raw **u16** mapped into a float range:
  `fVar5 = (float)uVar3 * _DAT_147f4fad8 * param_1[1] + fVar4;` with
  `_DAT_147f4fad8 = 1.5259021893143654e-05 = 1/65535`, `param_1[0]` = range base,
  `param_1[1]` = range span, clamped to `[base, base+span]`.
* `FUN_14087b4a0` (0x14087b4a0): 2 raw u32 (8 B) read as two packed quaternions and
  multiplied (`*param_3 = (fVar4 * fVar9 - fVar8 * fVar5) + fVar3 * fVar10 + fVar6 * fVar7;`).
* `FUN_14087a8d0` (0x14087a8d0): **control byte + up to 3 quantized components**:
  `bStack_18 = **(byte **)(param_4 + 0x10);` (control byte, bits 1/2/3/4 = which of the 4
  components are present, bits 5..6 = number of components, bit 0 = sign),
  `fVar7 = (float)bVar1 * _DAT_147f50680 - _DAT_147f506a8;` with
  `_DAT_147f50680 = 0.005545935593545437 (= 0.70710678/127.5)`,
  `_DAT_147f506a8 = 0.7071067690849304 (= 1/sqrt(2))`, then
  `fVar8 = SQRT(_DAT_147efe900 - fVar8);` (`_DAT_147efe900 = 1.0`) for the 4th component.
  -> **unit quaternion / normal from 1 control byte + up to 3 bytes (max 4 bytes)**.

---

## 4. ALCReplicatedState member offsets (VERIFIED) and the field->reader join

`FUN_142a35db0` pushes, for each property, a 16-byte entry `{namePtr, memberOffset}` into
two group vectors (`+0x360` inside an `AUX` object and `+0x370` inside the state object;
also `+0x720` for the second 0x3b0-byte sub-object). Recovered with a python
abstract-execution over the full raw listing (A-names2.log / A-join.log; 54 entries):

```
member                        state offset   descriptor     reader       wire
idRel                         +0x7d8         0x1480ff310    0x142a42d40  u8 (low byte of u16 id)
timeOffsetRel                 +0x858         0x1480ff310    0x142a42d40  u8
worldPosRel                   +0x910         0x1480ff0f0    0x142a43330  3 x u8
rotation                      +0x9b0         0x1480ff4e8    0x142a43380  1 + 0..3 bytes (quaternion)
lookDir                       +0x960         0x1480ff478    0x142a434b0  1 + 0..3 bytes (quaternion)
slayerStateId                 +0xac0         ?              ?            ?
slayerStateIdStarted          +0xb60         ?              ?            ?
slayerSequenceId              +0xbe0         ?              ?            ?
slayerStateId                 +0xae8         ?              ?            ?
slayerStateIdStarted          +0xb80         ?              ?            ?
slayerSequenceId              +0xc08         ?              ?            ?
slayerStateId                 +0xb10         ?              ?            ?
slayerStateIdStarted          +0xba0         ?              ?            ?
slayerSequenceId              +0xc30         ?              ?            ?
slayerStateId                 +0xb38         ?              ?            ?
slayerStateIdStarted          +0xbc0         ?              ?            ?
slayerSequenceId              +0xc58         ?              ?            ?
slayerSeqTimeRel              +0xcb0         ?              ?            ?
slayerSeqTimeAbs              +0xc88         ?              ?            ?
slayerSeqTimeRel              +0xd08         ?              ?            ?
slayerSeqTimeAbs              +0xce0         ?              ?            ?
slayerSeqTimeRel              +0xd60         ?              ?            ?
slayerSeqTimeAbs              +0xd38         ?              ?            ?
slayerSeqTimeRel              +0xdb8         ?              ?            ?
slayerSeqTimeAbs              +0xd90         ?              ?            ?
idAbs                         +0x7b8         0x1480ff2a0    0x142a42da0  u8 (high byte of u16 id)
timeOffsetAbs                 +0x838         0x1480ff2a0    0x142a42da0  u8
worldPosAbs                   +0x8c0         0x1480ff408    0x142a433d0  u32 + u32 + u16 = 10 B
scopeTimeBlob0Data0           +0x10c0        0x1480ff820    0x142a43140  varint count(<=33) + N u8
scopeTimeBlobEx               +0x11c8        0x1480ff820    0x142a43140  varint count(<=33) + N u8
scopeTimeBlob1Data0           +0x1148        0x1480ff820    0x142a43140  varint count(<=33) + N u8
teleportAndMigrationId        +0xe38         0x1480b9980    0x14279e210  u8
scopeData                     +0xed8         0x1480ff5c8    0x142a42e60  prefix varint (1..5)
scopeInfoBlob                 +0xf20         0x1480ff7a0    0x142a43230  varint count(<=177) + N u8
globalFragTags                +0xde0         0x1480ff730    0x142a42fd0  12 x u8 = 12 B
aiAngleToDesiredFacing        +0xa00         0x1480ff160    0x142a42f30  u32
wpnaccrystance                +0xa28         0x1480ff558    0x142a42f80  half float (2 B)
wpnaccrymvmnt                 +0xa50         0x1480ff558    0x142a42f80  half float (2 B)
scopeTimeBlob0Data1           +0x10e0        0x1480ff820    0x142a43140  varint + N u8
scopeTimeBlob1Data1           +0x1168        0x1480ff820    0x142a43140  varint + N u8
timeAnchor                    +0x7f8         0x1480ff398    0x142a43500  u64 (8 B)
dataBits                      +0x878         0x1480b9980    0x14279e210  u8
moreDataBits                  +0x898         0x1480b9980    0x14279e210  u8
combinedExtraNetworkData      +0x1450        0x1480b9980    0x14279e210  u8
segmentedStamina              +0xf00         0x1480b9980    0x14279e210  u8
gritBrokenCounter             +0xeb8         0x1480b9980    0x14279e210  u8
shapeCastFilter               +0x1470        0x1480ff5c8    0x142a42e60  prefix varint
slayerScriptLayers            +0xa78         0x1480b9980    0x14279e210  u8
slayerScriptFlags             +0xa98         0x1480ff5c8    0x142a42e60  prefix varint
scopeTimeBlob0Data2           +0x1100        0x1480ff820    0x142a43140  varint + N u8
scopeTimeBlob0Data3           +0x1120        0x1480ff820    0x142a43140  varint + N u8
scopeTimeBlob1Data2           +0x1188        0x1480ff820    0x142a43140  varint + N u8
scopeTimeBlob1Data3           +0x11a8        0x1480ff820    0x142a43140  varint + N u8
quantization                  +0x938         0x1480ff160    0x142a42f30  u32
```

Independent cross-check of the offset column **VERIFIED**: `worldPosAbs` is documented
both by the name->offset table (`+0x8c0`) and by the position code:

```c
undefined8 FUN_142a3cdc0(longlong param_1,undefined8 param_2)   // 0x142a3cdc0
{
  FUN_142a273b0(param_1 + 0x8c0);
  return param_2;
}
```

The 9 properties not in the list (`distGround`, `waterDepth`, `hitCharacterCounter`,
`hitStructureCounter`, `hitWorldCounter`, `forbiddenBounds`, `currentGridAccessibility`,
`scopelessInfoBlob`, `scopelessTimeBlob`) and the `slayerState*`/`slayerSeqTime*`
repeats are the ones whose 16-byte entries come from the *first* half of
`FUN_142a35db0` (before 0x142a36600, which my python pass excluded to keep the emulation
sound); their descriptors therefore were not joined. INFERRED: the 4 repeated
`slayerStateId/slayerStateIdStarted/slayerSequenceId` (stride 0x28) and the 4 repeated
`slayerSeqTimeRel/Abs` pairs are 4 "scope" instances of one sub-structure.

---

## 5. The world position (task step 4)

### 5a. Reader side
`worldPosAbs` descriptor 0x1480ff408, reader `FUN_142a433d0` (0x142a433d0):

```c
FUN_14087a270(auStackX_8,&uStackX_18,&uStackX_20,param_2);                  // u32 -> float bits
FUN_14087a270(auStackX_8,&uStackX_20,(longlong)&uStack_20 + 4,param_2);     // u32 -> float bits
func_0x000140870ab0(auStack_30,_DAT_147fd68d8,_DAT_147f4eb00,0);            // range object {min,span}
FUN_14087adf0(auStack_30,&uStack_38,auStack_18,param_2);                    // u16 -> min + u16/65535*span
*(undefined8 *)(param_1 + 0x10) = uStack_20;                                // 2 floats
*(undefined8 *)(param_1 + 0x18) = auStack_18[0];                            // 1 float
```
Constants read from the file: `_DAT_147fd68d8` = `-100.0f` (low dword; the qword packs
`-100.0, -360.0`), `_DAT_147f4eb00` = `1000.0f`.
=> **worldPosAbs wire = 4 B (u32, byte-swapped float bits) + 4 B (u32, byte-swapped float
bits) + 2 B (u16 linearly quantised over a 1000-unit span starting at -100)** = **10 bytes**.
VERIFIED: the code; INFERRED: that the two u32s are X and Y and the u16 is Z.

`worldPosRel` descriptor 0x1480ff0f0, reader `FUN_142a43330` -> `FUN_1417b1da0`
(0x1417b1da0):

```c
auStackX_10[0] = 0;
FUN_14087a190(auStackX_10,&uStackX_18);                     // byte 0 -> param_3[0]
FUN_14087a190(auStackX_10,&uStack_18,param_3 + 1,param_4);  // byte 1 -> param_3[1]
FUN_14087a190(auStackX_10,&uStack_16,param_3 + 2,param_4);  // byte 2 -> param_3[2]
```
=> **worldPosRel wire = exactly 3 bytes** (three quantised delta bytes), stored at
state+0x920..0x922 (worldPosRel record +0x10..+0x12).

External corroboration (2026-09-10): the published metric key of ratbuddy's `traffic-spectrum-diff`
report names `abs_rows` as "ALC rows with `world_pos.abs`", i.e. an independent implementation
reads the absolute world position out of ALC component rows in server-to-client channel-1
StateBundle traffic, alongside `records`, `action_rows` (`slayer_state_id[0]`) and
`sequence_only_rows` (`slayer_sequence_id[0]` without an action id). That is a field-name and
container match only, not an independent check of the byte layout above. Provenance and the
no-copy rule are in [REFERENCES.md](../REFERENCES.md).

### 5b. Assembly side
`FUN_142a273b0` (0x142a273b0) is the position getter used by ALC (2 call sites:
0x142a2ad04 in `FUN_142a2acd0`, and 0x142a3cdd0 in `FUN_142a3cdc0`, i.e.
`FUN_142a273b0(ALC + 0x8c0)`). Quoted:

```c
float * FUN_142a273b0(longlong *param_1,float *param_2)
{
  plVar7 = (longlong *)(**(code **)(*param_1 + 0x48))(param_1,auStackX_8);
  if (*plVar7 == -1) {                      // "absolute portion" not set
      ... log &UNK_1480fe8f0 ("DeltaCompression"), &UNK_1480fe900 ...
      ... FUN_1402b6e60(uStack_70,&UNK_1480fe8a0)  // "Absolute portion in delta compression wasn't set! We can't calculate the value."
  } else {
    fVar12 = *(float *)(param_1 + 2);                 // ALC+0x8d0
    fVar13 = *(float *)((longlong)param_1 + 0x14);    // ALC+0x8d4
    fVar14 = *(float *)(param_1 + 3);                 // ALC+0x8d8
    fVar11 = *(float *)((longlong)param_1 + 0x1c);    // ALC+0x8dc
    plVar7 = (longlong *)(**(code **)(param_1[10] + 0x48))(param_1 + 10);   // worldPosRel record (ALC+0x910)
    if ((((*plVar7 != -1) &&
         (cVar6 = (**(code **)(param_1[10] + 0x20))(param_1 + 10), cVar6 != '\0')) &&
        (((char)param_1[0xc] != -1 ||
         ((*(char *)((longlong)param_1 + 0x61) != -1 || (*(char *)((longlong)param_1 + 0x62) != -1))
         )))) && (cVar6 = (**(code **)(param_1[0xf] + 0x20))(), cVar6 != '\0')) {
      uVar1 = (undefined4)param_1[0x11];                                    // ALC+0x948 quantization
      fVar11 = (float)func_0x0001417163b0((char)param_1[0xc],uVar1);        // byte ALC+0x920
      fVar12 = fVar11 + fVar12;                                             // x = abs.x + delta.x
      fVar11 = (float)func_0x0001417163b0(*(undefined1 *)((longlong)param_1 + 0x61),uVar1); // ALC+0x921
      fVar13 = fVar11 + fVar13;
      fVar11 = (float)func_0x0001417163b0(*(undefined1 *)((longlong)param_1 + 0x62),uVar1); // ALC+0x922
      fVar14 = fVar11 + fVar14;
      fVar11 = fVar14;
    }
    *param_2 = fVar12; param_2[1] = fVar13; param_2[2] = fVar14; param_2[3] = fVar11;
  }
  return param_2;
}
```

Dequantiser for the three delta bytes (0x1417163b0):
```c
float FUN_1417163b0(byte param_1,float param_2)
{
  return param_2 * _DAT_14804d0b0 * (float)param_1 - param_2;
}
```
`_DAT_14804d0b0 = 0.007843137718737125 = 2/255`. So
`delta = quantization * (2*b/255 - 1)`, i.e. the byte maps linearly onto
`[-quantization, +quantization]`, and `0xFF` (`!= -1` in the guard above) is the
**sentinel meaning "no relative update"**. This matches the community's "worldPosRel
sentinel" hint.

INFERRED (not literally in the code): the quantization factor is the `quantization`
member (0x938, u32, read as 4 bytes with `FUN_14087a270`); the absolute position is
`(ux, uy from byte-swapped float bits, uz from the u16 range quantization)`, and the final
world position = absolute + dequantised relative delta for each of X, Y, Z. The 4th float
(W) is copied from Z in the code (`fVar11 = fVar14; ... param_2[3] = fVar11;`).

`FUN_142a42eb0` (a 1-byte quantised float field reader) uses the same 1/255 pattern:
```c
*(float *)(param_1 + 0x10) = (float)((uint)abStackX_18[0] << 2) * _DAT_147f40048 - _DAT_147efa334;
```
with `_DAT_147f40048 = 0.003921568859368563 = 1/255` and `_DAT_147efa334 = 2.0f`, i.e.
`value = (4*b)/255 - 2` -> range `[-2, +2]` in steps of 4/255.

---

## 6. Concrete ALC wire layout (as shown by the readers)

```
record (group container, reader 0x142a436b0):
  u8   groupMask
  [g=0] if bit0: varint fieldMask0 (1..9 bytes, network-order prefix varint, masked to 54 bits)
                 then, in entry order, the reader of each set bit
  [g=1] if bit1: varint fieldMask1 ... same

field readers (bytes):
  u8                       1   0x142a42d40 (idRel, timeOffsetRel)
  u8 -> u16 high byte      1   0x142a42da0 (idAbs, timeOffsetAbs)
  u32                      4   0x142a42f30 (quantization, aiAngleToDesiredFacing)
  u64                      8   0x142a43500 (timeAnchor)
  half float               2   0x142a42f80 (wpnaccrystance, wpnaccrymvmnt)
  u8 -> float [-2,2]       1   0x142a42eb0
  prefix varint            1..5 0x142a42e60 (scopeData, slayerScriptFlags, shapeCastFilter)
  u32+u32+u16              10  0x142a433d0 (worldPosAbs)
  3 x u8                   3   0x142a43330 (worldPosRel, 0xFF = sentinel)
  1 + 0..3 u8 (quaternion)      0x142a434b0 (lookDir), 0x142a43380 (rotation)
  12 x u8                  12  0x142a42fd0 (globalFragTags)
  varint(n<=33) + n x u8        0x142a43140 (scopeTimeBlob0/1Data0..3, scopeTimeBlobEx)
  varint(n<=177) + n x u8       0x142a43230 (scopeInfoBlob)
  1 byte bool (+optional)       0x142a43020
  u8                       1   0x14279e210, 0x1417b3c60 (dataBits, teleportAndMigrationId, ...)
```
There is **no float32 raw reader** anywhere in this set: every float arrives as either
byte-swapped u32 bit pattern, half float, or a u8/u16 quantisation with an explicit
scale/offset. VERIFIED.

---

## 7. What remains unknown / not verified in the budget (~40 min of Ghidra wall time)

1. **The `(tag, typeIndex 11)` dispatch to the ALC reader was not found.** The value
   envelope 0x146af20d0 (0x146af20d0..0x146af340) has only two call sites, both inside
   `FUN_14175ccc0`, and I could not tie that path to typeIndex 11 in the remaining time.
   The link I did prove is: ALC type name -> `FUN_142a3b050` -> `FUN_142a35db0` schema ->
   descriptor blocks -> readers. Whether the observed
   `[tag][type-ref=0x0b][flag][payload]` records select these readers via the registry
   handler's vtable is **not verified**.
2. Which of the two groups (`groupMask` bit 0 vs bit 1) is the "Absolute" and which is the
   "Delta/Relative" set is **INFERRED** from the Rel/Abs naming and from the low/high byte
   readers (`0x142a42d40` low byte, `0x142a42da0` `<<8` high byte) - not proven by a
   dispatch table.
3. The descriptors/readers of `slayerStateId(+0xac0/+0xae8/+0xb10/+0xb38)`,
   `slayerStateIdStarted(+0xb60..+0xbc0)`, `slayerSequenceId(+0xbe0..+0xc58)`,
   `slayerSeqTimeRel/Abs(+0xc88..+0xdb8)` are not in my join (they are registered in the
   first half of `FUN_142a35db0`). Their wire sizes are unknown.
4. `distGround`, `waterDepth`, `hitCharacterCounter`, `hitStructureCounter`,
   `hitWorldCounter`, `forbiddenBounds`, `currentGridAccessibility`, `scopelessInfoBlob`,
   `scopelessTimeBlob`: names present in `.rdata` but no offset/reader recovered.
5. `FUN_1417b3c60`/`FUN_1417b11d0`/`FUN_1461ac530`/`FUN_14158a220` (used by a few field
   readers) were only partially resolved; in particular the exact byte counts of the
   `scopeData`/`scopeInfoBlob` inner structure are not proven.
6. I did not verify the interpretation of the two byte-swapped u32 values of `worldPosAbs`
   as X/Y, nor which of the 4 floats `FUN_142a273b0` outputs is the game's X/Y/Z.
7. `FUN_142a436b0`'s own caller (who invokes it as a field reader) is not known: it has
   no direct `call` xref, only `.rdata` pointer references, so it is invoked through the
   descriptor vtable; the caller chain from the network layer is not established.

---

## 8. Addendum: the missing half of the schema is recovered (2026-09-10, later run)

Items 3 and 4 above are resolved; the authoritative field table now lives in
`alc-protocol-reference.md` section 3.2 (63 bits, each with member offset, reader and wire width).

What was done, in case it has to be repeated:

1. `DumpAlcSchema.java` (in `Tools/nw_capture/experimental/offline/ghidra/`) decompiles a function and
   then lists every operand that points into a data range, resolving each target to its string, its
   first qword and the qword at `+0x30`. Run against `FUN_142a35db0` it produced the whole builder
   (`private/decoder-state/ghidra-alc/alc-schema-C.txt`).
2. The builder assigns each field's descriptor to the block at its member offset (`param_1[N] =
   &UNK_<descriptor>`), and at the end pushes one 16-byte `(name pointer, block pointer)` entry per
   bit. `DumpStrings.java` resolved those name pointers (`alc-names.txt`), which gives the exact
   registration order: idRel, timeOffsetRel, the slayer families, worldPosRel, rotation, lookDir,
   idAbs, timeOffsetAbs, worldPosAbs, ... quantization. So the earlier claim that the missing fields
   live in a first half that was not emulated was wrong - they are in this function, as vector
   families whose *element* codecs are set by separate initialisers.
3. The family elements carry no static descriptor, so the four element initialisers
   (`0x142a38ed0`, `0x142a38ea0`, `0x142a35830`, `0x142a38e70`) were disassembled with `Sweep.java`
   and decompiled; `DumpQwords.java` resolved the descriptors they install
   (`private/decoder-state/ghidra-alc/alc-descriptors.txt`).

Consequences worth keeping in mind: `slayerStateId`, `slayerSequenceId` and `slayerSeqTimeRel` are
prefix varints or quantised bytes, `slayerStateIdStarted` is a u16, `slayerSeqTimeAbs` is a half
float, and the `scopeTimeBlob*Data*` bytes are plain u8 - which corrects the guess that they were
`varint <= 33` vectors.

