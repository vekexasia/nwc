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
| 2071 | DamageReceiverComponentClientFacet_OnDamageDealt | source id u64 byte-reversed, target id u64, source id, attack id u64 (zero on damage-over-time ticks, 1 s apart), flags u16, u8 count, entries as above |
| 2570 | ActionListComponentClientFacet_OnServerSpreadshotProcessed | pellet records (blunderbuss) |
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
