# Offline framing findings (S1, S2)

Results of steps S1 and S2 of [position-decoder-plan.md](position-decoder-plan.md). All
numbers come from the two probe scripts, which are the reproduction path:

```sh
.venv-capture/bin/python Tools/nw_capture/experimental/offline/probe_framing.py \
  Tools/nw_capture/captures/offline-position-scratch/ledger.bin
.venv-capture/bin/python Tools/nw_capture/experimental/offline/probe_type_ids.py \
  Tools/nw_capture/captures/offline-position-scratch/ledger.bin --u32-every-byte
```

Ledgers used: `captures/offline-position-scratch/ledger.bin` (session 475be10d, the Test
teleport ledger, 1.5 MB) and `captures/proton_20260909_213557/dtls/ledger.bin` (22.6 MB,
used only as a second sample).

## S1: the in-channel frame (success)

**The signature reported by the community is not in our captures.** `0x970C0A5D` appears
0 times in the teleport ledger (both endiannesses, raw file and every Carrier payload) and
once incidentally in the 22.6 MB ledger, inside an unchannelled outbound Carrier message.
The note does not apply to this layer or this build.

**The marker the decoder already guessed is real.** On the reassembled IN channel-1 stream,
`00 01 08 01` occurs 4119 times (teleport) and 49960 times (22.6 MB sample). Immediately
after it a u32 little-endian counter increments by exactly 1 across consecutive occurrences:
96.4% and 97.7% of the gaps. These are consecutive messages of one stream, not coincidences.

**The frame closes.** On the teleport ledger, writing `a` and `b` for consecutive marker
offsets, `len` for the u16 big-endian value at `a + 12`:

| tail bytes after the body | messages | share |
|---|---:|---:|
| exactly 1 | 2658 | 64.5% |
| exactly 2 | 848 | 20.6% |
| exactly 3 | 448 | 10.9% |
| 1 to 3 (total) | 3954 | 96.0% |
| rejected at this offset | 164 | 4.0% |

So the message layout is:

```
00 01 08 01            marker, 4 bytes
u32 LE                 counter, +1 per message on this stream
04 01 01 00            four bytes, constant in this session
u16 BE                 body length
body                   body length bytes
varint (VLQ)           trailer, 1..3 bytes in practice
```

Worked example: message at offset 1, `len = 0x004A = 74`, next marker at offset 90, so
`89 = 4 + 4 + 4 + 2 + 74 + 1`.

The earlier `STANDARD_CONSTANT` hypothesis (`01 01 01 01 00 00` after the marker) is wrong:
the bytes after the marker are the counter, not a constant.

The trailer is a variable-length integer, and the encoding is now known from the code, not
guessed. `FUN_140877970` writes and `FUN_14087b5c0` (422 bytes, decompiled and read directly)
reads a prefix-coded u32: 1 byte `0xxxxxxx` (7 payload bits), 2 bytes `10xxxxxx` (6 bits),
3 bytes `110xxxxx` (5), 4 bytes `1110xxxx` (4), 5 bytes `11110xxx` (3), with the payload
shifted out of the first byte. This is **not** the 7-bit continuation (LEB128) form, and an
earlier version of this note wrongly assumed that one; the numbers below are with the
verified decoder.

Measured with the verified decoder: the frame closes on 3602 of 4118 consecutive pairs
(87.5%) in the teleport ledger, and the chain resynchronises 514 times, i.e. for 13% of
messages the header + `u16` length + trailer model does not describe where the next message
starts (residuals are ±1 and ±2 bytes). Two further checks on the same ledger: 4114 of the
4119 markers are consecutive messages with no marker in between, and only 3 markers are
never used as a boundary, so the markers themselves are trustworthy there and the 13% is a
real gap in the model, not measurement noise.

The 22.6 MB session is different, and now measurably so: 17852 of its 49960 markers are never
used as a boundary (36% are occurrences inside bodies), only 6.0% of pairs close with this
model, and its bytes at `+8..+11` are mostly `01 01 00 00` instead of `04 01 01 00`. It is a
different message shape and S3 must not assume the teleport ledger's layout applies to it.

Open in S1: what the trailer *means* (its 1-byte values are spread, e.g. 112, 116, 108, 55, so
it is not a plain counter) and why 13% of messages need a resync.

## S2: type identifiers (not met)

With the frame known, the body can finally be read from its true start. Findings:

- Bodies open with five varints that are near-constant: `1, 1, 16, 11, 1` in 3292 of 3954
  framed messages. The first varying value is varint 5, over 25 distinct values, with the
  low three bits almost always set: 7, 103, 23, 231, 8199, 8295, 14343, 6151, 111. That looks
  like a bit-packed presence/flag mask rather than an identifier.
- Bodies contain repeated elements delimited by the 4-byte tag `01 10 0b 01`, 3 to 10 per
  body, 30174 occurrences in total. Right after the tag is one varint whose low three bits
  are almost always `0b111`; it takes 66 distinct values, and no shift of it yields a small
  bounded identifier set (60 distinct values even after shifting by 3).
- **Nothing resolved.** None of the recurring 32-bit values at any body offset resolves in
  `128_serialize.json` (4332 distinct class-name crc keys, 6468 element `nameCrc`, 326
  elementIds) or in `087_typeregistry.json` (3487 dense `index`, sparse `typeIndex`, uuid).
  For example `0x010b1001`, the most frequent value at any offset (30174 hits), is in none of
  those namespaces. The u16 range check is uninformative (40.5% of even-offset u16 values
  fall inside 0..3486, which byte data does on its own).

Conclusion for S2: the wire does not carry the registry identifiers as raw crc or index
values at fixed offsets in this layer. The identifier, if present, is bit-packed inside the
per-element structure, so its meaning has to come from the code, not from guessing offsets.
That is exactly S3: decompile the `Unmarshal` handler of a chosen type at the address recorded
in `087_typeregistry.json` and read the bit layout there, using the framed bodies of the
teleport ledger as ground truth.

### Where the type identifiers are not, and where the names live

Checked with `Tools/nw_capture/experimental/offline/probe_registry_static.py`, which parses
our own `NewWorld.exe` (179 MB, image base 0x140000000) instead of running it:

- The community registry dump describes **our** build: all 3487 of its uuids appear as literal
  strings in the local executable (case-insensitive scan of uuid-shaped tokens; 1651 of them in the
  exact uppercase form, 1835 in lowercase), and all 312 entries that carry a name have that name
  present.
- But the dump only names 312 of its 3487 entries, and none of those names is a
  `*ReplicatedState` type. The types we need are missing from the dump, not absent from the
  game.
- Our executable does contain the state names, but not all of them in the same form, and that
  decides whether a state can be read off the image at all. `ALCReplicatedState` is a plain literal
  in `.rdata` (raw `0x80fd590`; 3 occurrences in the file, 2 of them in `.rdata`), and one static
  record at raw `0x80fd3c0` holds the name pointer, a `.text` pointer table and the ASCII uuid in
  .NET byte order, which is how its property list was recovered. `PlayerComponentReplicatedState`
  is not: both of its occurrences are in the `.data` blob of mangled symbol names (raw
  `0xa1d2f60`, and `0xa24774e` inside the symbol), **no pointer references either**, so there is no
  descriptor record and no property list to read from it.
- The mangled symbols in `.data` carry the namespace per type, for example
  `InstallRegistrationHook@VPlayerComponentReplicatedState@MB@@@Hub@Amazon@@YA_NXZ`; among the 133
  `InstallRegistrationHook@V*ReplicatedState@<ns>@@` occurrences, `MB` is the common one (104),
  against `Javelin` (28) and `ClientMessages` (1).
- The runtime registry that carries `index`/`typeIndex` and the `Marshal`/`Unmarshal`
  addresses is therefore assembled at run time: the file gives names, vtables and code
  addresses, not the indexed table.

S3 needs a decompiler, and one is now installed and working:

- JDK 21 (Temurin, installed with `mise install java@temurin-21`; the machine default stays
  Java 8, nothing global was switched) and Ghidra 12.1.3 in
  `~/.local/share/ghidra/ghidra_12.1.3_PUBLIC`, with `ghidra` and `ghidra-headless` wrappers
  in `~/.local/bin`.
- Ghidra refuses project paths that contain dot-directories, so the project lives in
  `~/ghidra-projects/nw` (459 MB), not under `~/.local`.
- Our executable contains the community's handler code at the addresses recorded in the
  dump, which is why their Ghidra renamer scripts (`AzSerializeContextRenamer.java`,
  `AzModuleComponentDescriptorRenamer.java`, driven by `128_serialize.json`) apply to our
  binary.
- Full auto-analysis of a 179 MB binary is not needed. Import with `-noanalysis` takes
  about a minute, and `ghidra/Sweep.java` disassembles a window at a given virtual address,
  creates the function and decompiles it:

```sh
ghidra-headless ~/ghidra-projects nw -process NewWorld.exe -noanalysis \
  -scriptPath Tools/nw_capture/experimental/offline/ghidra \
  -postScript Sweep.java 0x1407c6510:2048
```

Verified output: `0x1407c6510` (the `Unmarshal` slot shared by many registry entries, RVA
`0x7c6510`) decompiles to a real 89-byte function that forwards into `FUN_146154e90` and
`FUN_146160ae0`. Several addresses can be passed in one run.

MCP is not needed for this: pi has no MCP support by design, and driving Ghidra headless with
scripts gives the same capability the community's Ghidra-MCP setup gave their assistant.

### The live registry, read from the running process (S3b)

With the game already running, `frida-server.exe` was started inside the existing Proton prefix
(`run -- wine frida-server.exe --listen 127.0.0.1:27943`, no Steam start, no game launch) and
Frida 17.9.10 from `.venv-capture` attached read-only (`Process.enumerateRanges`,
`Memory.scanSync`, `readByteArray`; no interceptor, no write, no spawn). The game process was
left running. Findings:

- The table is found by scanning writable memory for the vtable pointer `NewWorld+0x84cb580`:
  exactly 3487 hits, the same count as the community dump, and all 3487 live uuids match its
  uuid set.
- Entry layout confirmed in memory, with `index` and `typeIndex` proven by correlation over all
  3487 entries: `+0x00` vtable, `+0x18` 16 uuid bytes, `+0x28` name storage (inline for len<=15),
  `+0x50` u32 index, `+0x54` u32 typeIndex, `+0x48` per-type handler object. Live dump:
  `/tmp/nwc/live-registry.json` (3487 entries plus `ALCReplicatedState` descriptor block).
- **The registry does not carry names for 3175 of its entries.** Only the same 312 that the
  community dump names have a name; for the rest the name field is an empty string in our build
  too, so `*ReplicatedState` names cannot be recovered from the registry at all. 42 entries end
  with `::State` (e.g. `Replicate::State` index 85, `ActorMover::State` index 3322).
- `ALCReplicatedState` is one of the unnamed ones. Its name exists only in a static descriptor
  in `.rdata`, verified byte for byte here: at VA `0x1480febc0`, `+0x00` is a pointer to the
  string `ALCReplicatedState` (VA `0x1480fed90`) and `+0xa8` holds the ASCII uuid
  `01b0664b-3ab6-44a6-87e3-8c69d40e0365`, which occurs exactly once in the file. That uuid is
  registry entry **index 1075, typeIndex 11**, name empty. So the name -> registry slot mapping
  is available only where such a static descriptor exists, one type at a time.

### Reading the bodies again with the code-verified encoding

The 7-bit continuation form used earlier in this note was wrong; with the prefix-coded decoder
the numbers change:

- Only 39.1% of bodies (1545 of 3954) decode as a pure varint stream with no leftover, so bodies
  are mixed content, not a varint sequence.
- The varint value `11` appears in **every** framed message, most often as the fourth varint
  (position 3, 3392 of 3954). `11` is also the typeIndex of `ALCReplicatedState`, which makes
  "the fourth field is a type index" tempting and unproven: the value is constant, so it is
  equally consistent with a constant envelope field. Disambiguating this needs a capture whose
  messages are known to be of several different types, or the code that writes position 3.
- No frame contains the varint `1075` (the ALC index), so the wire does not appear to carry the
  registry `index` field.

### Who writes the body: live tracing of the serialization path

Attempted with the same read-only attach route (log-only `Interceptor.attach`, no writes to
game memory), game left running:

- The low-level writer every serialized field goes through is `NewWorld+0x87bcc0`
  (sink vtable `NewWorld+0x8582d68`, slot `+0x40`); ~13k to 18k writes in a 20 second window.
  Field writers observed, with their write sizes: `0x876c8f` (1 byte, 1783 calls), `0x877a84`
  (1 byte, 990), `0x877abb` (1 byte, 940), `0x877d29` (9 bytes, 510), `0x87710a` (8 bytes, 144),
  `0x876d2c` (4 bytes, 135), `0x876cca` and `0x877a6a` (2 bytes), `0x877c94`, `0x876cf8`.
- **Negative result on the varint writer**: hooked `NewWorld+0x877970` for 2445 calls and
  logged caller plus value; no caller ever wrote the value 11, so the `0b` at body position 3
  does not come from the varint writer. The observed writes are a repeating ~14-write pattern
  with small values (0, 1, 12, 26, 32, 61, 62, 92, 95, 108, 136, 144, 152, 153, 205, 349, 1589).
- **Negative result on the marker**: across 6000 sampled writes spanning 17 sink instances, no
  sink's reconstructed byte stream contains `00 01 08 01`, and the pattern exists 4 times as
  data in `.rdata` and zero times as a code immediate in `.text`. Either those writes belong to
  other subsystems, or the sink objects are reused across messages so that grouping writes per
  sink does not reconstruct single messages.

So the question "what is the field at body position 3" is still open. The next experiment that
can actually answer it is to trace `0x87bcc0` without truncation while a capture session runs
(the repo's own tooling), then align the traced outgoing bytes against the OUT channel-1
messages in the resulting ledger by content, which labels every write of a known message.
A cheaper static alternative that helps either way: decompile the twelve field-writer addresses
listed above, which yields the primitive toolkit (which function writes a u8, u16, u32, varint
or string) that any body reader needs.

Trace artifacts: `/tmp/nwc/trace_varint.js`, `trace_sink.js`, `trace_sinkbytes.js`,
`bytes-trace.json`, runner `/tmp/nwc/run_trace.py`.

### Capture with the write trace: correlation works, and it moves the question

Ran the repo's own Proton capture path (`Tools/nw_capture/experimental/offline/capture_with_trace.py`,
same frida-server-inside-the-prefix route as `capture_proton.py`, attach to the running game) with
the extra probe `probe_write_trace.js` loaded in the same Frida session. Session
`captures/proton_20260910_154332-writetrace/`: ledger 1,133,958 bytes, 104,071 traced writes, game
left running.

- **Correlation confirmed**: 12-byte windows taken from the traced writes appear in the captured
  OUT channel-1 stream in 1015 of 1045 sampled cases (926 for OUT channel 0, 934 for the
  unchannelled OUT stream, only 99 in the IN stream, which is coincidence level). So the traced
  writes are the outgoing serialized content, and they can be read as labelled ground truth:
  every field of an outgoing message has a known writer address.
- **The OUT channel-1 stream has no markers**: 3211 occurrences of `00 01 08 01` in the IN stream,
  **zero** in the OUT stream. The marker + counter + `u16` length frame is therefore an *inbound*
  shape, not a symmetric application frame.
- **This invalidates hunting for "who writes body position 3" on the client**: the body of an IN
  message is produced by the server, so no client writer explains it. What the client gives us is
  the schema dialect on the outgoing side, and the reader side for inbound messages.

Labelled example from the captured outgoing stream (bytes, then the writer that produced them):
`6f 56 40 d4 | 00 00 00 d1 | 66 1b 83 a4 f0 df 9c a3 ed 68 c7 b7 7a 3f cc 81` where the 16-byte
value comes from caller `0x6b0f694`; then `00` from `0x6167143`, `01` from `0x616722f`, two bytes
`b5 18` from `0x877a6a`, two 8-byte values from `0x87710a`, and `00 01 00 00` from four `0x876c8f`
calls. The writer list matches the one recorded in the section above.

Next experiment, now that the direction is clear: hook the *reader* path (`0x140878610` bounded
copy plus the read driver `0x146160ae0`) instead of the writer, which yields the field order the
client parses from an inbound message and therefore what body position 3 actually is.

### Reader trace: the bounded copy is not the DTLS inbound parser

Same capture route, with `probe_read_trace.js` hooking `0x140878610` (bounded byte read, reader
struct `+0x08` end / `+0x10` cursor) and `0x14087b5c0` (prefix-coded varint decode). Session
`captures/proton_20260910_154811-writetrace/`: 54,444 reads, 115,830 varint decodes, 715 monotonic
cursor runs reconstructed per reader context.

- **No correlation with the inbound stream**: 12-byte windows taken from the reconstructed read
  bytes match the captured IN channel-1 stream at 0.23 to 0.47%, which is chance level, and none
  of the 715 reconstructed parse runs appears verbatim in it. So `0x140878610` is used by other
  subsystems, not by the parser of the channel-1 inbound messages.
- Read sizes were almost all 1 byte (51,356 of 54,444), with 3,038 reads of 16 bytes.
- The prefix varint decoder `0x14087b5c0` is a generic utility: its most frequent decoded values
  are `11` (23,863), `0` (16,229), `5` (12,914), so the `11` seen at body position 3 is not
  evidence of anything by itself.

Where the inbound parse actually happens is still unknown, but the promising anchor is the read
driver `0x146160ae0` (three virtual stages, all required) rather than the byte-copy helper: the
object it is handed carries a vtable, and in this build each vtable is followed in `.rdata` by the
inline type name and uuid, so hooking the driver should label inbound parses by type directly.

Artifacts: `Tools/nw_capture/experimental/offline/probe_read_trace.js` (copy kept as
`/tmp/nwc/probe_read_trace.js`), `capture_with_trace.py`, sessions
`captures/proton_20260910_154332-writetrace` (write trace) and
`captures/proton_20260910_154811-writetrace` (read trace).

### Parse-label trace: the AZ read driver is never called in normal play

Hooked the read driver `0x146160ae0` for 60 seconds, recording the vtable of the value object, the
caller and the reader cursor, with the same capture route (session
`captures/proton_20260910_155107-writetrace`). Result: **zero calls**. The hook itself was armed
(the runner fails loudly if a probe has no `install` and returns exit 99 on a runner error; this run
took the normal timeout path, and the DTLS ledger hooks in the same session logged their own
`dtls_hook_installed` / `dtls_ready`).

So the inbound replication traffic we capture does not go through the AZ `SerializeContext` reader
while the game runs normally. Combined with the earlier result, the picture is asymmetric:

| Direction | Format evidence |
|---|---|
| OUT channel 1 | AZ serializer, verified: 1015/1045 sampled 12-byte windows of the write trace appear in the captured stream; field writers known by address |
| IN channel 1 | different format: marker + incrementing u32 counter + `u16` length + body + prefix-coded varint, no AZ driver involvement |

The IN shape matches what the community describes as GridMate replication (`ReplicatedStateBundle`,
`type_idx`, bitmask-gated option fields), which is a different serialization path from the AZ one
that `128_serialize.json` and the renamer scripts cover.

One more negative check: the pattern `00 01 08 01` exists 4 times in `.rdata` and has **zero**
qword-pointer or dword-RVA references from code, so nothing compares those bytes as a constant.
The only evidence that it is a message header is structural: 4114 of 4119 occurrences are
consecutive with no occurrence in between, and the u32 that follows increments by exactly 1 in
96.4% of the gaps.

Artifacts: `probe_read_trace.js`, `probe_parse_labels.js` (copy in `/tmp/nwc/`),
`capture_with_trace.py`, sessions `captures/proton_20260910_154332-writetrace` (write trace),
`captures/proton_20260910_154811-writetrace` (read trace),
`captures/proton_20260910_155107-writetrace` (parse labels).

### S3c: concrete result - the inbound type identifiers are registry `typeIndex` values

This is the first decoded wire identifier, with names.

What was measured. Hooking the prefix-coded varint reader (`0x14087b5c0`) and logging the reader
cursor for every decode showed that the client parses the channel-1 bodies we capture through it:
109,693 of 128,461 decodes in a 45 second window had their cursor bytes inside the captured IN
stream, and they come from a handful of call sites. The dominant ones are

| call site | count | what it is |
|---|---:|---|
| `0x61ad00f` | 37,303 | `FUN_1461acfe0`: read a varint, then either 16 raw bytes (value 0) or a table lookup by that value (bounds-checked table with 16-byte elements) |
| `0x6af237f`, `0x6af2134` | 33,775 / 24,893 | `FUN_146af20d0`: read a varint, measure the bytes consumed, build 24-byte records |
| `0x6ae4541` | 7,008 | another value reader |

Hooking that first reader (`probe_uuid_refs.js`) and logging the values it reads gives the
identifier space. In 45 seconds of live play: 16,346 reads over 55 distinct values, min 8,
max 7048. Every one of the 55 resolves to a live registry `typeIndex`, and 16 of them are above
3486, so they cannot be dense `index` values: the space is exactly the registry's `typeIndex`.

| typeIndex | reads | registry index | uuid | name |
|---:|---:|---:|---|---|
| 11 | 8,567 | 1075 | `01B0664B-3AB6-44A6-87E3-8C69D40E0365` | `ALCReplicatedState` |
| 349 | 45 | 74 | `6A379FB8-0BDD-43A1-AB3E-9843D7BE8CD3` | `PingMsg` |
| 335 | 15 | 72 | `038CD847-0653-4243-9A26-936E3BD7F312` | `TimeSynchMsg` |

The remaining 52 ids resolve to registry entries (uuid and index) but have no name anywhere we
can read: the registry name field is empty for them and no static descriptor was found for their
uuid. Names for the two message types come from the community dump; the name for
`ALCReplicatedState` was verified byte for byte in the binary (file offset `0x80fd468` holds its
uuid, and `uuid_offset - 0xA8` holds the pointer to the string).

So the actor/local-channel state type that carries the player is identifiable on the wire as
`typeIndex 11`, and it is the most frequent identifier in that stream.

Reproduce:

```sh
# capture with the id probe (same Proton attach route as capture_proton.py)
.venv-capture/bin/python Tools/nw_capture/experimental/offline/capture_with_trace.py 45   # uses probe_uuid_refs.js
# resolve the observed ids to registry entries and names
.venv-capture/bin/python Tools/nw_capture/experimental/offline/decode_wire_type_ids.py \
  --trace Tools/nw_capture/logs/<run>_uuid_refs.log \
  --registry Tools/nw_capture/captures/offline-position-scratch/live-registry.json
# frame and record decoding over a ledger
.venv-capture/bin/python Tools/nw_capture/experimental/offline/decode_in_bodies.py \
  Tools/nw_capture/captures/offline-position-scratch/ledger.bin
.venv-capture/bin/python -m unittest discover -s Tools/nw_capture -p 'test_*.py'
```


#### Closing the last gap: the index really is the registry typeIndex

The step above was indirect: it showed that the observed values all coincide with registry
`typeIndex` values, but not that the table the reader indexes *is* the type table. That is now
verified directly. Hooking `FUN_1461acfe0` and recording, per call, both the varint at the reader
cursor and the 16 bytes the function returns gives (index, value) pairs that can be checked
against the live registry:

| measurement | result |
|---|---|
| reference reads captured in 40 s | 11,858 |
| reads where `table[index]` equals the registry uuid of `typeIndex == index` | **11,858** |
| reads where it does not | **0** |

Top entries: index 11 x10,512 -> `01B0664B-3AB6-44A6-87E3-8C69D40E0365` (`ALCReplicatedState`),
index 8 x1,216 -> `8A40AEC2-AE07-4F92-9BF3-78FC0CC94FDF`, index 3780 x63, index 349 -> `PingMsg`,
index 335 -> `TimeSynchMsg`, index 6484 -> `UpdateMsg`.

So the wire value is a registry `typeIndex`, the table the reader indexes holds the same uuids,
and the names come from the registry or from the static descriptor. `ALCReplicatedState` is about
89% of the type references on that stream, which makes it the concrete target for the position:
the community's notes put the spawn world position, `idRel`, `timeOffsetAbs` and `timeOffsetRel`
inside `ALCReplicatedState`, and these are exactly the channel-1 bodies that `decode_in_bodies.py`
can already frame and cut into records.


#### Position: candidate coordinates exist, the trajectory does not

`probe_position_candidates.py` extracts every plausible float32 pair from every framed body and
links them across frames by proximity. Measured:

| ledger | framed bodies | plausible float pairs | tracks | longest track |
|---|---:|---:|---:|---|
| Test teleport | 3602 | 1110 | 323 | 22 frames, x in [16287, 16346], y in [100, 364] |
| 20260909_213557 | 3002 | 1477 | 788 | 32 frames, x = 2.0, y in [1, 420] |
| live 20260910_160453 | 1373 | 435 | 199 | 6 frames |

Concrete candidates from the teleport capture: `(15290.3, 4442.3)` stable for 20 frames,
`(15312.7, 2316.6)` for 18, `(15226.3, 7899.3)` for 15, `(16345.8, 364.1)` for 22. They cluster in
the same region (x around 15200-16400), which is what world coordinates of entities in one zone
would look like.

But this does not decode the position: no track shows a trajectory, no track shows the teleport
jump, and float32 triples do not coexist at a stable layout. The parse evidence says why: the
inbound codec reads only 1, 2, 7 and 16 byte chunks, never 4, so replicated values are not read as
raw floats. Positions are therefore quantised or delta-encoded inside the record payloads, and the
pairs above are most likely fields of other structures (interest/bundle data) that happen to look
like coordinates.

What would settle it: a capture in which the player walks a known path for ~30 seconds. A real
position track must then show a monotone, small-step trajectory over hundreds of frames, and the
teleport capture's short stationary tracks must be explainable as other entities.

#### Ghidra: how the inbound packets are actually unpacked

Read directly from the binary (decompiled with the headless sweep, addresses are RVAs):

| address | primitive |
|---|---|
| `0x87a190` | u8: one raw byte, end-checked |
| `0x87a1c0` | u16, then a transform that is an import thunk (`jmp [IAT]`, i.e. network -> host order) |
| `0x87a220` | u32, same transform shape |
| `0x87ad90` | u64, same transform shape |
| `0x87a3d0`, `0x87a330` | varint length (bound `0x2ffff`) then that many raw bytes: a length-prefixed blob |
| `0x878610` | bounded raw copy of n bytes, hard `cursor + n <= end` check |
| `0x87b5c0` | prefix-coded varint, 7/6/5/4/3 payload bits (verified against its own writer) |
| `0x61acfe0` | type/uuid reference: varint index into a 16-byte table, index 0 means 16 inline bytes (verified 11,858/11,858 against the live registry) |
| `0x6a6ddb0` | vector of u16: varint count (rejects > 100), then elements |
| `0x6ae44f0` | delta-map entry: varint value plus the byte count it consumed |
| `0x6af20d0` | value envelope: varint, consumed-size measurement, builds a 24-byte record |

**There is no float32 reader anywhere in this path.** That is a structural fact read from the
code, not an inference: the codec never reads four raw bytes as a float, so replicated numeric
values arrive as integers (with an order transform), as varints, or inside blobs.

Combined with the type reference (byte `0x0b` = `typeIndex` 11 = `ALCReplicatedState`, verified),
the body shape of a real message is a sequence of records:

```
[envelope tag][type-ref][flag byte][payload 4..7 bytes]   repeated
```

A byte-annotated example from a live capture (frame #1370, 256 bytes) shows the tag at `+5`
(value 16), the type reference at `+6` (11), the flag at `+7`, then the payload, and the same
pattern repeating at `+56`, `+80`, `+96`, `+111`, ... with the envelope tags 5, 16, 102, ...

Two consequences verified in this pass:

- The float32 pairs that looked like coordinates do **not** reproduce the teleport: across 123
  candidate slots, zero show the "stable, jump larger than 1000, stable again" signature. They are
  coincidental byte patterns, not positions.
- The registry's handler objects carry the type name **in UTF-16**: the entry with typeIndex 335
  reads `RegistrationResponseMsg` and the one with 6484 reads `BaseGameChatMessage`. The
  community dump maps those names to other slots, so its name column is misaligned; the name read
  from the handler object is intrinsic to the entry.

The `.rdata` region around VA `0x148552230` holds the serialization registry: class name strings
followed by arrays of method pointers, one of which is the 7-byte blob reader. Walking that region
is the route to the per-class field readers, and therefore to the ALC payload grammar.

### The position is decoded

Static analysis of the type factory closed the last gap. `FUN_142a3b050` allocates the type named
`ALCReplicatedState` and calls the schema builder `FUN_142a35db0`, which registers 48 ordered
properties whose names sit in `.rdata` at `0x1480ffa84`: `idRel`, `timeOffsetRel`, `worldPosRel`,
`rotation`, `lookDir`, ... `idAbs`, `timeOffsetAbs`, `worldPosAbs`, `quantization`, ... The field
framing is `FUN_142a436b0`: one **group mask** byte, then per active group a **field bitmask**
varint, then for every set bit the field reader through the descriptor vtable. The readers are
typed (u8, u8->u16, u16, varint, u8->float, u32, u64, half, quaternion, counted vectors) and the
position ones are:

| field | reader | wire |
|---|---|---|
| `worldPosAbs` | `0x142a433d0` | 10 bytes: two byte-swapped float32 then a quantised u16 |
| `worldPosRel` | `0x142a43330` | 3 bytes: three quantised deltas, `0xff` = no update |

The u32 reads go through an import thunk that converts network to host order, so the two floats are
big-endian on the wire. The u16 is quantised into `[-100, 1000]`; big-endian is the order that
yields a stable value for a standing entity.

Evidence from a walking test: the operator's character walked twice, and a capture while tracing
exactly those two readers (`nw_pos_probe.js`) produced

```
track 1: 378 samples  x[8786.66..8893.83] z[3003.97..3126.63] y[58.03..74.35]
    x steps between updates: 2.014, 2.081, 2.022, 2.07, 2.139, 2.128, 2.072, 2.07, ...
```

`x` advances monotonically in steps of about 2 units per update while `z` drifts slightly and `y`
stays inside a 16-unit band, which is what walking on a road looks like. Before and after the walk
the same track is flat. This is not a pattern match: the bytes are read by the reader the code says
reads the position.

Tools: `nw_pos_probe.js` (traces the two position readers), `decode_position.py` (log -> positions,
JSON/CSV), `nw_capture_probe.py` (attach and capture with any probe), `nw_vkeys.py` (hold keys in
the focused game with a focus guard), `nw_walktest.py`/`.sh` (drive and capture together).

Still inferred, not verified: which of the two floats is the north-south axis, the exact affine
mapping of the quantised third component (the `[-100, 1000]` constants were read, the pairing of the
per-entity scale argument was not), and the per-field bit order of the two field bitmasks.
## Status against the plan

| Step | Status |
|---|---|
| S1 framing | success: frame confirmed, with the trailer encoding now taken from the code (87.5% exact on the teleport ledger); marker and counter verified independently |
| S2 type table | partially answered: the registry holds uuid/index/typeIndex/handler for all 3487 types but **no names** beyond 312, so names must come from static descriptors or the binary, one type at a time |
| S3 one state's field layout | in progress: decompiler installed and working, shared codec grammar read and the varint scheme verified; no wire field has been tied to a named type yet |
