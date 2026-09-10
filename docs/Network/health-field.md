# Health field and the Vitals registry type

## Scope and conclusion

This is static analysis of the installed `NewWorld.exe`. No game process was started or
attached for this pass. Addresses are absolute virtual addresses for image base
`0x140000000`.

The Vitals network type in this build is:

```text
MB::VitalsComponentReplicatedState
UUID     0E721C70-2CDB-4E85-BAE4-D545FDC6D25B
typeIndex 15 (0x0f)
```

It is **not** the ALC type `ALCReplicatedState` (`typeIndex 11`), and it is not the
local RTTI type named `VitalsReplicatedData`. The registry entry has an empty stored
name, but the binary's registration-hook string identifies the C++ type.

The important limitation is narrower than previously reported: this type uses a custom
marshal/unmarshal handler rather than the ALC `FUN_142a35db0` schema builder, but its
constructor still builds a group-aware replicated field table. `FUN_14671E040` registers the
fields through `FUN_141775C60`; the member codecs are initialized with descriptor objects, and
`qword(descriptor + 0x30)` is the field reader used by the custom unmarshal path. The table and
widths below are now recovered statically. A live type-15 payload is still needed to validate the
field ordering and values in a capture.

## Type identity evidence

| Evidence | Address/value |
|---|---|
| Registration-hook string | `0x14A24B440`: `.?AV<lambda_1>@?1???$InstallRegistrationHook@VVitalsComponentReplicatedState@MB@@@Hub@Amazon@@YA_NXZ@` |
| Type-name substring in that string | `0x14A24B46E`: `VitalsComponentReplicatedState@MB@@@Hub...` |
| UUID string parsed by the getter | `0x1484C7E38`: `0e721c70-2cdb-4e85-bae4-d545fdc6d25b` |
| UUID getter | `FUN_146820FE0` |
| Handler vtable | `0x14852C768` |
| Registration lambda invoke | `FUN_1465B2760` |
| Marshal handler | `0x1407F8B00` |
| Unmarshal handler | `0x1465B0DD0` |

`FUN_146820FE0` parses the UUID at `0x1484C7E38`, stores the vtable address
`0x14852C768`, and returns the resulting type descriptor. `FUN_1465B2760` calls that
getter and then the Hub registration routine `FUN_1461A9740`.

The six qwords at the vtable are:

| vtable offset | address | role |
|---:|---:|---|
| `+0x00` | `0x1465B10E0` | destructor |
| `+0x08` | `0x1465B1180` | get empty value |
| `+0x10` | `0x1465B09C0` | create instance |
| `+0x18` | `0x1465B0AA0` | copy value |
| `+0x20` | `0x1407F8B00` | marshal |
| `+0x28` | `0x1465B0DD0` | unmarshal |

The historical read-only registry entry for this UUID reports `index: 3241` and
`typeIndex: 15`. The same UUID and type index occur in the saved registry attachment.
The registry entry itself has `name: ""`; the C++ name above comes independently from
the installed binary's registration-hook string.

### `VitalsState` name walk-back

The literal `VitalsState` hits are not a type descriptor: they occur in
`MatchingVitalsState` / `NotMatchingVitalsState` (`EntityQueryCondition`) and in a log string
around `0x1480A0575`. A qword-reference search for the literal hits at `0x1480A0428`,
`0x1480A0443` and `0x1480A0575` returns no descriptor pointer. Therefore task 1 has no
descriptor associated with the literal `VitalsState` string.

The actual type was found independently through the registration hook above. Its handler
descriptor/vtable is `0x14852C768`; its custom field builder is `0x14671E040`. Calling the
generic `table(0x14671E040)` helper prints `0 properties, 18 descriptor slots` because it
only recognizes the ALC builder shape. Following the custom `FUN_141775C60` registrations
produces the 19-row table below.

## Recovered Vitals fields

### Component-side registrations

`FUN_14671E040` constructs the Vitals component-side object and calls
`FUN_141775C60` with the following names and member addresses. The member offsets are relative
to the state object passed to the builder. The descriptor and reader columns are the codec objects
used by the custom unmarshal path; they are not offsets into the outer record payload.

| property name | name VA | member offset | descriptor | `qword(descriptor+0x30)` reader | implied wire width |
|---|---:|---:|---:|---:|---|
| `HealthAmount` | `0x14855F7B0` | `+0x7C0` | `0x1480FF160` | `0x142A42F30` | 4 B (u32) |
| `StaminaAmount` | `0x14855F7C0` | `+0x7E8` | `0x1480FF160` | `0x142A42F30` | 4 B (u32) |
| `ManaAmount` | `0x14855F7D0` | `+0x810` | `0x1480FF160` | `0x142A42F30` | 4 B (u32) |
| `HealthMax` | `0x14839AFF8` | `+0x838` | `0x1480FF160` | `0x142A42F30` | 4 B (u32) |
| `StaminaMax` | `0x14823D1F8` | `+0x860` | `0x1480FF160` | `0x142A42F30` | 4 B (u32) |
| `ManaMax` | `0x14855F7F8` | `+0x888` | `0x1480FF160` | `0x142A42F30` | 4 B (u32) |
| `HealthTickRate` | `0x14855F818` | `+0x8B0` | `0x1480FF558` | `0x142A42F80` | 2 B (half) |
| `StaminaTickRate` | `0x14855F828` | `+0x8D8` | `0x1480FF558` | `0x142A42F80` | 2 B (half) |
| `ManaTickRate` | `0x14855F838` | `+0x900` | `0x1480FF558` | `0x142A42F80` | 2 B (half) |
| `healthChangeFlags` | `0x14855F898` | `+0x928` | `0x14855EA40` | `0x146951470` | 1 B |
| `replicatedAfflictionsHotData` | `0x14855F848` | `+0x970` | `0x14855EAB0` | `0x14694EDF0` | variable: count and entries |
| `replicatedAfflictionsColdData` | `0x14855F868` | `+0xC18` | `0x14855EB50` | `0x14694EB20` | variable: count and entries |
| `vitalsData` | `0x14855F888` | `+0xEC0` | `0x14855EBF0` | `0x1469515B0` | 1 B absent, 18 B present |
| `vitalsId` | `0x14855F8B0` | `+0xF48` | `0x1481B7D50` | `0x1432D9460` | 4 B (u32) |
| `vitalsCategoryId` | `0x14855F8C0` | `+0xF70` | `0x1481B7D50` | `0x1432D9460` | 4 B (u32) |
| `vitalsLevel` | `0x14855F8D8` | `+0xF98` | `0x1480B98A0` | `0x1417B3620` | 4 B (u32) |
| `invulnerability` | `0x14855F8E8` | `+0xFC0` | `0x1480B9980` | `0x14279E210` | 1 B |
| `displayImmuneWhenInvulnerable` | `0x14855F8F8` | `+0xFE0` | `0x1480B9980` | `0x14279E210` | 1 B |
| `maxHealth` | `0x1483E2BC0` | `+0x1000` | `0x1480FF638` | `0x142A42E10` | 2 B (u16) |

These are component/object offsets from the state object passed to `FUN_14671E040`. The
custom unmarshal path is nevertheless connected to them: `FUN_1465B0DD0` calls
`FUN_146160AE0`, whose state vtable dispatches to `FUN_1417B4110`; that routine reads the
group masks and calls `FUN_1417B43C0`, which invokes each selected member codec's vtable
`+0x30` reader. The widths above are therefore codec-implied wire consumption, before the
per-group mask bytes and any container framing.

For the requested health candidates: `HealthAmount` is `+0x7C0` / 4 B; `HealthMax` is
`+0x838` / 4 B; and the separately named lower-case `maxHealth` is `+0x1000` / 2 B.
There is no registered `HealthRegen` row. `HealthTickRate` at `+0x8B0`, decoded by the
2-byte half reader, is the closest registered regen-related field. Keep `HealthMax` and
`maxHealth` distinct until a type-15 payload or setter correlation resolves their semantics.

### Nested local RTTI types

The local `VitalsStatData` type is the clearest storage-level representation of a
health value. Its type name is at `0x148084C88`; its registration function is
`FUN_1468F7E3D`. These local members are storage-only RTTI entries; they are not separately
registered by `FUN_141775C60`, so no direct network reader is attached to these rows.

| local property | member offset | local data size |
|---|---:|---:|
| `m_amount` | `+0x08` | 4 B |
| `m_max` | `+0x0C` | 4 B |
| `m_tickRate` | `+0x10` | 4 B |
| `m_tickCapThreshold` | `+0x14` | 4 B |
| `m_wasFullyDepleted` | `+0x18` | 1 B |
| `m_healthChangeFlags` | `+0x20` | 16 B |

`VitalsReplicatedData` is a separate local RTTI type at `0x148081ED8`, registered by
`FUN_1468F7785`. Its recovered fields are:

| local property | member offset | local data size |
|---|---:|---:|
| `m_vitals` | `+0x08` | 0x90 B |
| `m_currentAfflictions` | `+0x98` | 0x90 B |

The reflection metadata describes `m_vitals` as an unordered map whose value is
`VitalsStatData`. Therefore `m_amount` and `m_max` are the best-supported candidates
for current and maximum health, but that map relationship is not a wire-layout proof.
`VitalsData` at `0x148081F18` is another local type and is not the network registry
type; it contains death-door state rather than the health amount.

## Custom handler and wire-status evidence

The top-level handler remains custom, but its unmarshal flow enters the recovered field table:

```c
lVar1 = FUN_14671E040(param_3);
FUN_146160AE0(lVar1, param_2, param_4);
/* vtable +0x90 for the state is FUN_1417B4110 */
/* FUN_1417B4110 -> FUN_1417B43C0 -> selected member vtable +0x30 reader */
if (*(char *)(param_2 + 1) == '\0') {
    FUN_14055C530(lVar1 + 0xe30);
    FUN_142770740(lVar1 + 0xc18);
    FUN_14029B5A0(lVar1 + 0xb88);
    FUN_143A1FD80(lVar1 + 0x970);
    FUN_1467327E0(lVar1 + 0x7c0);
    FUN_141653110(lVar1);
}
```

`FUN_1417B4110` reads one or more mask bytes, then `FUN_1417B43C0` walks the selected
fields in each 800-byte group. The latter calls the codec object's vtable at `+0x30`;
this is why the descriptor readers in the table are part of the custom network path, not
just an unrelated reflection table. The mask and container framing add bytes beyond each
field width.

The held historical ledger `/tmp/nwc/B-ledger.bin` contains only record type `0x0B`
(`ALCReplicatedState`) in the tested channel-1 stream. It contains no observed type
`0x0F` record, so these static readers have not been validated against a live Vitals payload.

To recognize one in a future channel-1 capture, consume the record envelope first:
`[V1 varint][0x01][V2 varint][TYPE varint][group mask][payload]`, then select records whose
`TYPE == 15` (encoded as the single byte `0x0f` in this build). A raw `01 01 ... 0f` byte
search is not sufficient because the same bytes can occur inside other payloads. The group
mask and selected field masks then determine which table readers run.

## Verified, inferred, and unresolved

### Verified

- The installed binary contains a Hub registration hook for
  `MB::VitalsComponentReplicatedState` at `0x14A24B440`.
- Its UUID is the string at `0x1484C7E38`; the UUID getter associates it with vtable
  `0x14852C768`.
- The handler vtable identifies marshal `0x1407F8B00` and unmarshal `0x1465B0DD0`.
- The saved registry entry for that UUID has `typeIndex: 15`.
- `FUN_14671E040` registers the 19 named component fields and their member offsets.
- The descriptors and `+0x30` readers in the table are initialized by the builder and
  reachable from the custom unmarshal dispatch.
- The primitive readers establish the scalar widths shown in the table; container and
  optional-structure readers are variable or conditional as marked.
- The local `VitalsStatData` layout has `m_amount` at `+0x08` and `m_max` at `+0x0C`.
- The held ledger's observed record type histogram has no type `0x0F` record.

### Inferred

- `VitalsStatData.m_amount` and `m_max` are the most likely current/max health
  storage fields.
- `HealthAmount` and `HealthMax` are component-side names corresponding to those
  health concepts.
- `HealthTickRate` is the closest registered counterpart to the unreferenced
  `HealthRegen` string; its half-width codec suggests a distinct rate representation.
- A future Vitals record, if emitted in the same registry framing, would use the
  varint type index `15` (`0x0F` as a one-byte value). This has not been observed here.

### Could not establish

- The exact group/property order and mask bits in a live type-15 payload.
- Whether the lower-case `maxHealth` field at `+0x1000` is the network max-health
  value, a derived aggregate, or a separate gameplay/UI value.
- Whether the 4-byte amount/max codecs represent floats directly or apply quantization
  or another transform after their raw-width read.
- A live payload example for `MB::VitalsComponentReplicatedState`.

## Exact commands

All Ghidra queries used the fast PyGhidra wrapper, not a new long headless analysis.
The scripts were session-local files under `/tmp` and are not repository inputs.

```bash
cd /home/andrea/git/personale/new-world-capture

# Identity, vtable, names, getter, registration invoke, unmarshal, and constructors.
.venv-ghidra/bin/python \
  Tools/nw_capture/experimental/offline/ghidra/nw_ghidra.py \
  --script /tmp/health_field_final_query.py

# The generic ALC helper shows the shape mismatch; it returns 0 properties and 18 descriptor slots.
NW_GHIDRA_LOCK=/tmp/nw-ghidra-health-table.lock \
  .venv-ghidra/bin/python Tools/nw_capture/experimental/offline/ghidra/nw_ghidra.py \
  --script /tmp/health_table_required.py

# The custom table extraction follows FUN_141775C60 registrations and descriptor initialization.
NW_GHIDRA_LOCK=/tmp/nw-ghidra-health-custom.lock \
  .venv-ghidra/bin/python Tools/nw_capture/experimental/offline/ghidra/nw_ghidra.py \
  --script /tmp/health_query_custom_table.py

# Registry lookup from the saved historical read-only registry dump.
python3 - <<'PY'
import json
for uuid, entry in json.load(open(
    'private/open-world-discord/attachments/087_typeregistry.json'
))['data']['m_list']:
    if entry.get('typeIndex') == 15:
        print(uuid, entry)
PY

# Independent binary string check for the C++ registration hook.
BIN='/home/andrea/.local/share/Steam/steamapps/common/New World/Bin64/NewWorld.exe'
strings -tx "$BIN" | rg -F 'VitalsComponentReplicated'

# Historical channel-1 record type histogram.
.venv-capture/bin/python -c "
import sys, collections
sys.path[:0] = ['Tools/nw_capture/experimental',
                'Tools/nw_capture/experimental/offline']
from decode_in_bodies import channel_stream
s = channel_stream('/tmp/nwc/B-ledger.bin', direction='in', channel=1)
h = collections.Counter(s[i+2] for i in range(len(s)-4)
                        if s[i] == 0x01 and s[i+1] == 0x10 and s[i+3] in (1, 3))
print(len(s), h)
"
```

The registry and ledger commands above read saved artifacts only. They do not start the
game, capture traffic, or attach to a process.
