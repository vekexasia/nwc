# RMI messages (typed messages that are not state chunks)

Recorded by `nw_join_probe.js` as `rmi_samples` (`[ts, type, hex]`, first 64 bytes after the type
reference), listed by catalog name with `decode_rmi.py --log <log>` and parsed by the functions in
that file. Client-facet RMIs start with the 16-byte uuid of the receiving facet; every facet of the
player's own entity ends in the same 8 bytes (`31df13d046e908f8` on 2026-09-11).

| type | name | body after the facet uuid |
|------|------|---------------------------|
| 4118 | ChatComponentClientFacet_ReceiveChatMessage | u8-length strings: sender character uuid (36 chars), sender name; 6 bytes (byte 0 = channel, 2 seen); text; 12 zero bytes; 01; Steam id string; 01 03 |
| 293 | ChatComponentClientFacet_ReceiveBatchedChatMessages | u8 count, then the same records |
| 3601 | VitalsComponentClientFacet_OnDamage | receiver id u64, flags u16, damage / receiver max health f32, hit position xyz f32, u8 count, count x (damage type u8, amount f32, f32 unread) |
| 2071 | DamageReceiverComponentClientFacet_OnDamageDealt | source id u64 byte-reversed, target id u64, source id, attack id u64 (zero on basic shots and on damage-over-time ticks), flags u16 (0002 on the 1 s ticks; direct hits 0x2100; bit 0x4000 = critical: same attack id, median 3,811 against 2,943 and 1,494 against 1,251, the +30 % of a crit; bit 0x8000 = 0 damage, absorbed or immune; bit 0x0800 and bit 0x0001 unread), u8 count, entries as above |
| 4299 | VitalsComponentClientFacet_ClientSyncDeathRecap | u8 length, the killer's vitals name key (`@Invasion_Spearman_VitalsName`, English through the name book's display column), u32, u16, f32 last hit (257.0), f32 the player's max health (9237.0), then 1.0 multipliers |
| 2415 / 3916 | AITargetableComponentClientFacet_OnSelectedAsTarget / OnUnSelectedAsTarget | the u64 id of the mob that starts / stops targeting the player; the page lists them as "targeted by", named when the id was bound by a dealt hit |
| 2570 | ActionListComponentClientFacet_OnServerSpreadshotProcessed | pellet records (blunderbuss) |
| 1628 | PlayerManagerSelfIdentificationMsg | direct message: 05, the player's character uuid (16 bytes, the same uuid the chat sender string carries), more ids; the live page names e1 from a chat line sent by this uuid |
| 4140 | SocialComponentClientFacet_PlayerDataResponse | 16 bytes, 01, uuid string, name string, then level and flags (inspected players) |
| 3 | RegistrationResponseMsg | direct message: session ids and the build string `[RETAIL].Javelin.1.365.6031.6017213` |
| 349 / 335 | PingMsg / TimeSynchMsg | direct messages, 8 bytes |

Evidence (live 20260911-201741, the player's death at 20:45): 34 OnDamage hits sum to 9,811
against 9,659.16 max health plus regen ticks of 43.9; `fraction * maxHealth` reproduces the amount
to 0.01. The player's own hits carry two entries when the weapon has an elemental gem (type 05
1158.8 + type 0e 392.7, the 25 % conversion). The damage type byte is the `IntID` column of
`javelindata_damagetypes.datasheet`: 3 Standard, 5 Thrust, 8 Arcane, 10 Lightning, 11 Corruption,
14 Nature (the player's weapon: Thrust plus a Nature gem; the corrupted casters: Corruption and
Lightning).

Open: the trailing f32 of every entry (0.49 to 0.68, constant per attack), the flags bits, the
attack id hash.
