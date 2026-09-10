# Open World Discord: decoding notes

Community research notes, not our own findings. Source: the "Open World" Discord
(guild `1501266699750740029`), channels `#general` and `#ask-a-question`, exported
on 2026-09-10 through the operator's own logged-in web session. Attachment links are
signed and expire, so the material they point to was downloaded locally (see
`Provenance` at the end). Nothing here is verified by us.

The project in that server is the New World private-server/emulator effort
(Aeternum / build 6031). The capture checklist tracked there
(`Coldzer0/Aeternum-World` -> `Tools/nw_capture/CAPTURES_TODO.MD`) is the same list
we keep in `Tools/nw_capture/CAPTURES_TODO.MD`, and `#file-sharing` is the forum
where each mechanic gets its capture and a "Needs Verified" state.

## Where the material is

| Place | Content |
|---|---|
| #ask-a-question | real reverse-engineering work: structs, RVAs, marshalers, registry dumps, codegen |
| #general | coordination, tool/repo links, capture sharing, roadmaps, coverage |
| #file-sharing (forum) | one thread per capture, status "Needs Verified", tags per mechanic, sub-thread "New capture" |
| #dev-blog / #faq / #announcements | status, rules, FAQ, donation |

## Files shared in the server

| Date | Author | File | What it is |
|---|---|---|---|
| 2026-06-05 | mixednuts | `secure_connection.rs` 50 KB | DTLS/OpenSSL transport between custom client and real server |
| 2026-06-10 | mixednuts | `typeregistry.json` 2.6 MB | type name -> unmarshal address (`NewWorld+0x...`) |
| 2026-06-12 | danigt91 | `open-world-capture-v1.zip` | batch installer/runner for the capture tooling |
| 2026-06-12 | graphx_npc | `mining.zip` 11 MB | example capture (Ebonscale mining run) |
| 2026-06-14 | _cink_ | `boulder_next_to_silex.zip` | example capture |
| 2026-06-14/16 | aangairbender, ratbuddy | `message.txt` x5 | raw message dumps, idx-8 bundles, spawn lists |
| 2026-06-18 | mixednuts | `serialize.json` 16.6 MB | RTTI serialization descriptors, input of the codegen |
| 2026-06-18 | mixednuts | `module.json` 737 KB | `AZ::Module` reflection data |
| 2026-06-19 | mixednuts | `modules.zip`, `AzSerializeContextRenamer.java` 91 KB, `AzModuleComponentDescriptorRenamer.java` 18/39 KB | Ghidra renamers driven by serialize.json; modules.zip covers all modules |
| 2026-06-20 | mixednuts | `nw-serialize-codegen.exe` 35 MB | generates marshalers from serialize.json |
| 2026-06-30 | aangairbender | `Capture_TODO_list_6-30-2026.txt` | 496 unique messages seen, +52 in a week, plus what is missing |
| 2026-07-01 | ratbuddy | `capture-triage.html` 1.7 MB | seen/missing message triage viewer by gameplay area |
| 2026-07-06 | .denacious | `NW_packet_capture_TODO_Opus_4.8__05062026.md` 20 KB | capture checklist |
| 2026-05-12 | ratbuddy | `runtime_load_sweep_20260512_185649_summary.md` | tick-time sweep against the 30 Hz budget |

## External sources referenced

- `github.com/Coldzer0/Aeternum-World` - capture tooling, `.pak` unpacker/repacker, analysis docs.
- `github.com/nw-private-server/first-light` - `docs/capture-guide.md` (Frida capture), hosts redirect, no-trust-patch.
- `ow.ratbuddy.com/` - status dashboards of the same private-server effort: `/completeness/`
  (per-action evidence ledger; contains no position or transform entry) and `/spectrum/`
  (retail-vs-current-build replication diffs). See [REFERENCES.md](../REFERENCES.md).
- `github.com/ratbuddy/nw-sim` - server-side world sim (tick budget ~33333 us at 30 Hz), movement
  bounds. UNVERIFIED: the repository returned HTTP 404 on 2026-09-10 and the public `ratbuddy`
  account lists no New World server-simulation repository, so treat this as a historical reference.
- reddit `r/newworldgame`, "Aeternum Legacy community-driven New World project".

## Wire format facts reported there

- Message V3 header: the first 4 bytes are the signature `0x970C0A5D`, not padding.
- Transport: DTLS 1.2 over UDP, record-layer version `0xFEFD`. Needs `DTLSv1_2_method`
  (removed in OpenSSL 4.x, present in 3.x and 1.1.1), a manually built `HelloVerifyRequest`
  cookie before OpenSSL takes over, and a single cipher `ECDHE-RSA-AES256-GCM-SHA384`
  (`SSL_CTX_set_cipher_list`), plus `SslOptions::NO_QUERY_MTU`.
- Reading the DTLS stream in Wireshark requires the session keys: kernel driver or injected DLL,
  which carries a ban risk. The no-trust-patch plus Frida hook route avoids it.
- Payload compression: LZ4, but only for some channels and message types, with a 4-byte prefix
  before the LZ4 stream (generic LZ4 tools fail if the prefix is kept).
- Every message has its own format and size. The old Lumberyard/GridMate format no longer
  matches, only similarities remain.
- Endianness: network types big-endian, memory types little-endian.
- Primitives seen: `AzString` (VarInt length + bytes), `IndexedPack`/`IndexedField`
  (u8 count, then u32 index + string), bitmask-gated Option fields in bit order (GridMate VLQ
  bitmask, `idRel` = bit 0 as u8 = `revision & 0xFF`), `VarU64DeltaMap<T>`, and a tagged
  "UUID or String" union (1 tag byte, then 16-byte UUID or length-prefixed string). A wrong
  marshaler for that union produced a permanent black screen.
- `ReplicatedStateBundle`: one missing or wrong codec makes every remaining byte garbage
  (decode drift, `type_idx == 0` in the middle of the array). Work state by state:
  `PlayerComponentReplicatedState`, `ALCReplicatedState`, `VitalsReplicatedState`,
  `GdeMetadataReplicatedState` (required for the character to appear),
  `PlayerHomeComponentReplicatedState` (`homePointList`, 158 entries in the initial bundle,
  parses to about 70 then breaks), `CampingComponentReplicatedState`.
  Player entities do not have `PositionInTheWorldReplicatedState`.
- RMI addressing: the two u64 at the head of a facet message are `owner_replica_id` (the replica
  that owns the facet) and `target_local_id` (the facet instance inside it).
- Useful addresses: `NewWorld+0x148552610` iterates DatasetContainer groups and reads an optional
  varint u64 per dataset; `NewWorld+0x6160a60` is `Amazon::Hub::FragmentCategoryToString(byte)`
  with 7 categories. Imagebase `0x140000000`, so `NewWorld+0x7ce8e0` = `0x1407CE8E0`.
- Derived data: `scatter_entity_id = ((ordinal+1) << 13) | ((region_y & 0x1f) << 8) | ...`.
- Client state machine, which explains why two captures of the same action can differ: the server
  never sets the client state, the GameConnection is a poller advanced by specific messages.
  10->11 is `RegistrationResponse`, 11->12 (`WaitingForActorGameConnection` ->
  `WaitingForSpawnPoint`) is the next gate message, 14 means the RSB landed plus the typed cascade
  (`RegistrationResponseMsg(3)` -> `CalendarConnection...`). Freshness gate: the client discards
  frames when the time since the last valid server frame exceeds a few hundred ms, so
  `timeOffsetAbs`/`timeOffsetRel` must stay set. Reference spawn bundle: ALC create at world
  position (9304, 2912, 85), identity rotation, `worldPosRel` sentinel `[255,255,...]`.

## Method that unblocked people there

- Ghidra plus an MCP server for the binary, ImHex for byte inspection.
- `serialize.json` plus the renamer scripts give the binary `AZ::*` names, then marshalers are
  generated by `nw-serialize-codegen.exe` instead of written by hand.
- Type names double as a roadmap: one `XComponent` per milestone.
- Coverage is tracked per message: 496 unique messages seen against roughly 3400 to map,
  about 400 decoded classes covering level 1-40 gameplay.
- LLMs are used there to write tooling, not to ingest raw captures.

## Provenance

- Exported 2026-09-10 from the operator's own logged-in Discord web session via Chrome DevTools
  Protocol, by hooking the client's own message fetches (no bot, no user token shared with
  third-party software).
- Local copies, inside this repo but gitignored (`/private/`): `private/open-world-discord/exports/`
  (raw JSON plus readable text) and `private/open-world-discord/attachments/` (the files in the
  table above, plus screenshots; video attachments were not downloaded). Local names are prefixed
  with the row index in `downloads.tsv`; `private/open-world-discord/README.md` maps the
  important ones, and `manifest.tsv` records every row.
- Discord message history is not ours; keep the exports private, they contain other people's
  messages and attachment links.
