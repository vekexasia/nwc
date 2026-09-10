# Where the player's health lives: Vitals name hunt (deepseek pass)

Scope: find the schema that carries the player's HP in the replicated protocol, using the method of
[alc-protocol-reference.md](alc-protocol-reference.md) section 1 (name string -> descriptor holding a
qword pointer to it -> property table). Sessions: PyGhidra via
`Tools/nw_capture/experimental/offline/ghidra/nw_ghidra.py` (see
[ghidra-workflow.md](ghidra-workflow.md)). All addresses are RVAs in `NewWorld.exe`. No game was
attached; the only runtime artifact touched read-only is the previously captured ledger
`/tmp/nwc/B-ledger.bin`.

**Bottom line: there is no schema join for a health field in this build.** `VitalsState` is not a type
name, no qword anywhere points to it, and every Vitals structure the binary names is either a C++
member list or a Hub component/message type whose uuid is not in the network type registry. The
scenario the task asks about (a Vitals record in the `[V1][0x01][V2][type][groupMask][payload]`
template) does not occur in the captures we hold: they contain exactly one record type, 0x0b.

## 1. Task 1: walking back from `VitalsState` - negative, and provably so

Sanity check of the method first (the ALC descriptor shape, reference 1.3):

```
find_bytes(qword 0x1480fed90 "ALCReplicatedState") -> 0x1480febc0     VERIFIED
qwords at 0x1480febc0: 0x1480fed90 0xffff 0x140294970 ...             (name pointer at +0x00)
```

Applied to the three `VitalsState` addresses, the method returns nothing:

| address | string | qword pointers to it | xrefs |
|---|---|---|---|
| `0x1480a0428` | `VitalsState` | none | none |
| `0x1480a0443` | `VitalsState` | none | none |
| `0x1480a0575` | `VitalsState` (inside a message) | none | none |

Reason (VERIFIED by reading the neighbours): none of the three is a type name. The first two are the
tails of the AI-behaviour-tree descriptor's property names, and the third is inside a log string:

```
0x1480a03f0 'TagFilter' 0x1480a03fc 'Center' 0x1480a0408 'RequiredTargetsFound'
0x1480a0420 'MatchingVitalsState'
0x1480a0438 'NotMatchingVitalsState'
0x1480a0570 "Both VitalsState values specified and identical, this is invalid in
              EntityQueryCondition '%s' in node '%s'"
```

`EntityQueryCondition` (0x1480a0388) is the descriptor that owns those property names. **Conclusion
(VERIFIED): the operator's grep hit is a substring of `MatchingVitalsState`/`NotMatchingVitalsState`,
not a replicated type.** There is no descriptor to report for task 1, because no descriptor exists.

`VitalsReplicatedState` (the old community name) is absent from this build. `VitalsReplicated` at
`0x148081ed8` is `VitalsReplicatedData`, a string in a mixed pool next to `Spawner`, `VitalsData` and
`javelin.*` console names, and it also appears inside an error message
(`keyVal (%d) out of range while converting VitalsReplicatedData!`, 0x14855f4f0). No qword points to
either occurrence.

Other Vitals name addresses from the task, with the same result:

| address | string | qword pointers |
|---|---|---|
| `0x147fc9edf` | `Vitals` (inside `g_debugVitals`, 0x147fc9ed8) | none |
| `0x147fcfdc5` | `VitalsVariant` | none |
| `0x147fd1e44` | `VitalsData` (`nw_getStaticVitalsData` area) | none |
| `0x147fd28d8` | `VitalsComponentClientFacet` | none |
| `0x14839aff8` | `HealthMax` | `0x14855f7e0` (see 2) |
| `0x14834a5ba` | `HealthRegen` | none |
| `0x14855ef7f` | `HealthRegenThreshold` | none |
| `0x147fd3424` | XML example `<Health bInvulnerable = "0" MaxHealth = "500" ...>` | none |
| `0x147fd3c16` | `MaxHealth` inside `Player CurrentHealth = %f and MaxHealth = %f` | none |
| `0x1481b78c7` | `MaxHealthChangeInVitalsSnapshot` inside the enum name `eGameModeParticipantFlag_IncludeMaxHealthChangeInVitalsSnapshot` (0x1483faca0) | none |

## 2. The one real pointer: the vitals member-name table (still not a schema)

`HealthMax` (0x14839aff8) is the only health-like name in the binary that is pointed at by a qword.
The holder is a static name/pointer table at **0x14855f7e0**, inside a cluster of Vitals C++ member
names (0x14855f490 .. 0x14855fa00):

```
0x14855f490 'SetCurrentHealth'          0x14855f4a8 'SetCurrentHealthMax'
0x14855f4f0 "... converting VitalsReplicatedData!"
0x14855f710 'm_health'  0x14855f71c 'm_mana'  0x14855f728 'm_stamina'
0x14855f788 'm_snapshot' 0x14855f7b0 'HealthAmount' 0x14855f7c0 'StaminaAmount' 0x14855f7d0 'ManaAmount'
0x14855f7e0  qword -> 0x14839aff8 'HealthMax'
0x14855f7e8  qword -> 0x14823d1f8 "StaminaMax\0StaminaRegenRate\0..."
0x14855f7f0  qword -> 0x14855f7f8 'ManaMax'
0x14855f800/808/810 -> 'HealthTickRate' / 'StaminaTickRate' / 'ManaTickRate'
0x14855f848 'replicatedAfflictionsHotData'  0x14855f868 'replicatedAfflictionsColdData'
0x14855f888 'vitalsData'  0x14855f898 'healthChangeFlags'  0x14855f8b0 'vitalsId'
0x14855f8c0 'vitalsCategoryId'  0x14855f8d8 'vitalsLevel'  0x14855f8e8 'invulnerability'
0x14855f950 'm_tickRate' 0x14855f9a8 'm_baseMax' 0x14855f9b8 'm_initialAmount'
0x14855f9c8 'm_baseTickRate' 0x14855f9d8 'm_baseRegenRate' 0x14855f9e8 'm_regenDelay'
```

`find_bytes(qword 0x14855f7e0)` is empty and none of the names is targeted by a code/data reference we
can reach, so **there is no builder (`table(builder_va)`) to print here**: this is a static name table
of the vitals attributes (HealthMax, ManaMax, HealthTickRate, ...), with no descriptor block and no
reader, therefore no wire width. INFERRED: it is the attribute/config set of the vitals component, not
a replication schema. There is no `health`/`maxHealth`/regen property table in the ALC sense to show.

## 3. Task 2/3: what the network registry says about Vitals types

The task-2 join is only possible against the type registry. Source: the 3487-entry registry dump in
`private/open-world-discord/attachments/087_typeregistry.json` (uuid -> index, typeIndex), the same
source used by `decode_wire_type_ids.py`; it agrees with this build on 3484/3487 uuids.

The binary holds `(name, uuid)` tables for the Hub component/message system. Joining them against the
registry gives the candidate record type bytes (a record's type byte is the typeIndex, e.g. 11 =
0x0b for ALC). The name -> uuid pairing is read from the table layout (a message name is followed by
its uuid(s)); for the entries with more than one nearby uuid the pairing is INFERRED and the uuid
addresses are given so it can be re-checked:

| binary name (address) | uuid (address) | typeIndex |
|---|---|---|
| `VitalsComponentClientFacet_ClientSyncDeathRecap` 0x14852d710 | `F5BCCF27-8788-40DB-B6B5-24121B119750` | **186** |
| `VitalsComponentClientFacet_OnRequestRevive` 0x148517360 | `56687d4c-7221-445c-9e1f-caa7bd627762` | **1335** |
| `VitalsComponentClientFacet_OnEnteredDeathsDoorInSiegeWarfare` 0x14851c0a8 | `3ac945ab-e8f0-4456-bffd-8597ec6fa9d8` | **2643** |
| `VitalsComponentClientFacet_OnDamage` 0x148522b60 | `290f24ab-b20b-4a75-a961-ff765e67a03d` | **3601** |
| `VitalsComponentClientFacet_Debug_SyncStatusModVitalsData` 0x1485274b8 | `9AD0F0BF-F3FA-424C-8369-062B34D1CB7D` / `D1D08F5B-...` | **3975 / 4256** |
| `VitalsComponentClientFacet_OnHealedPlayer` 0x148529568 | `4265E85B-7725-4CF3-91CD-E36B3983C135` | **5290** |
| `VitalsComponentClientFacet_ClientSyncDeathRecapForAllGameModeParticipant` 0x148517570 | `A2BBF0D3-A57E-4747-8A9C-CCACE3479A71` | **5197** |
| `VitalsComponentClientFacet_NotifyDamageNumberBusOnTrueDamageReceived` 0x148526160 | `5B0C96DC-927B-4238-9600-F8EE73A2D8B6` | **6792** |
| `VitalsComponentClientFacet_Debug_SyncVitalsSifficulty` 0x148517d38 | `AA38960E-0B8F-4D1E-A99D-3010CCE041B7` | **7030** |
| `VitalsComponentServerFacet_RequestSetCurrentHealth` 0x148527ca0 | `6343F0B7-0DF8-40C4-894D-9493E502DFB6` | **6277** |

Not in the network registry at all (so they can never be a top-level record type):

| name (address) | uuid (address) |
|---|---|
| `VitalsComponentServerFacet` 0x14853eb50 | `BD1ECA6B-532A-493C-AA76-C381CD9E773A` @0x14853eb70 |
| `VitalsSnapshotData` 0x14853eb98 | `6305B8E1-4229-434F-A9DE-5DD0F7D78B42` @0x14853ebb0 |
| `PersistentVitalsServerData` 0x14853ebd8 | `EDC8C08E-585F-4CE7-B802-F19994A41E02` @0x14853ebf8 |
| `VitalsStatModData` 0x14853d418 | `B1F68AD3-788A-47AE-B51C-3F02E34531DA` @0x14853d431 |

`VitalsSnapshotData` is a Hub snapshot/persistence structure (its neighbours in the same table are
`CooldownsState`, `GeneralCooldownData`, `PersistentCooldownData`), which is consistent with the rule
that members `vitalsData`, `healthChangeFlags`, `vitalsId`, `m_health` are serialized inside a
component container, not as an independent registry type.

**Empirical answer to task 3 (VERIFIED, measured on the captured ledger):** over the reassembled IN
channel-1 stream of `/tmp/nwc/B-ledger.bin` (450 308 bytes), the record tag `01 10 <type> <flag>` with
`flag in {1,3}` occurs 2746 times and **every single one has type byte 0x0b** (ALCReplicatedState);
there is no other type byte. None of the Vitals typeIndexes above (186, 1335, 2643, 3601, 4256, 5290,
6792, 7030, ...) appears in the capture.

So, in the captures we hold, no Vitals record exists to recognise. If it were replicated in that
shape, a Vitals notification would show up as

```
[V1 varint][0x01][V2 varint][<typeIndex as varint>][groupMask][payload]
```

with `<typeIndex>` from the table above (e.g. the death-recap message would be 186 = 0xba, not 0x0b),
i.e. a record whose type byte is not 0x0b. That is the detector to run on a future capture, together
with the ALC field map: HP is not among the 63 ALC fields.

## 4. Verified vs inferred

VERIFIED
- `VitalsState` is a substring of `MatchingVitalsState` / `NotMatchingVitalsState` of the
  `EntityQueryCondition` descriptor; no qword pointer, no xref (addresses in 1).
- The qword-pointer method works and is validated on ALC (`0x1480fed90` -> `0x1480febc0`).
- `HealthMax` is referenced only from the static name table at `0x14855f7e0`, which itself is
  unreferenced; no descriptor, no reader, no wire width.
- The Vitals member names in 0x14855f490..0x14855fa00 (`m_health`, `m_mana`, `m_stamina`,
  `HealthAmount`, `healthChangeFlags`, `vitalsData`, `m_baseMax`, ...) are C++/serialization member
  names, not ALC property names.
- The uuids of `VitalsComponentServerFacet`, `VitalsSnapshotData`, `PersistentVitalsServerData`,
  `VitalsStatModData` are absent from the 3487-entry network registry.
- The `VitalsComponentClientFacet_*` / `_ServerFacet_*` message uuids are in the registry and resolve
  to the typeIndexes in the table of section 3.
- The captured stream contains only record type 0x0b.

INFERRED
- The client's HP is carried either inside a container we have not indexed (a component-replicated
  state such as `PlayerComponentReplicatedState` 0x14a1d5160/0x14a24994e, a Hub facet replication
  path, or an ALC blob field) or by one of the Vitals message types above, which simply never appears
  in this capture.
- The health value is a float in the client (`Player CurrentHealth = %f and MaxHealth = %f`,
  `VitalsComponent::UpdateVitals: %s = %2.4f`); the wire form is unknown (reference 2.1 states there
  is no float32 reader in the ALC path).

COULD NOT ESTABLISH
- Any property table (name, member offset, descriptor, reader, wire width) for a health field: no
  Vitals descriptor, no builder and no reader was found, so there is nothing to print.
- Whether a Vitals notification ever reaches the client in a normal session: needs a capture with the
  death/revive/heal events and a type-byte histogram that includes one of the indexes in section 3.

## 5. Exact commands run

```bash
cd /home/andrea/git/personale/new-world-capture

# 1. name -> pointer walk-back, sanity check and Vitals names (scripts under /tmp, kept out of the repo)
.venv-ghidra/bin/python Tools/nw_capture/experimental/offline/ghidra/nw_ghidra.py --script /tmp/q2.py
#   qrefs(<va>): find_bytes(struct.pack('<Q', va)) ; read_ascii(va, 40)

# 2. context of the three VitalsState addresses (strings of 0x1480a0000..0x1480a0900)
.venv-ghidra/bin/python .../nw_ghidra.py --script /tmp/q3.py

# 3. the HealthMax pointer table and the vitals member cluster
.venv-ghidra/bin/python .../nw_ghidra.py --script /tmp/q4.py
.venv-ghidra/bin/python .../nw_ghidra.py --script /tmp/q10.py
.venv-ghidra/bin/python .../nw_ghidra.py --script /tmp/q11.py

# 4. (name, uuid) tables -> uuids -> registry typeIndex  (q14.py loads the registry inside the session)
.venv-ghidra/bin/python .../nw_ghidra.py --script /tmp/q14.py

# 5. registry lookups offline
python3 -c "import json; reg=json.load(open('private/open-world-discord/attachments/087_typeregistry.json')); ..."

# 6. record type histogram of the captured ledger
.venv-capture/bin/python -c "
import sys, collections; sys.path[:0]=['Tools/nw_capture/experimental','Tools/nw_capture/experimental/offline']
from decode_in_bodies import channel_stream
s=channel_stream('/tmp/nwc/B-ledger.bin', direction='in', channel=1)
h=collections.Counter(s[i+2] for i in range(len(s)-4) if s[i]==0x01 and s[i+1]==0x10 and s[i+3] in (1,3))
print(len(s), h)"
# 450308  Counter({11: 2746})
```
