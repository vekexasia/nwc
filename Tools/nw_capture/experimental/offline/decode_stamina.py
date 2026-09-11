"""StaminaComponentReplicatedState (typeIndex 4297): the stamina bar, as the server sends it.

Payload shape read from the player's chunks during a driven sprint and three dodges
(logs/20260911-130958_live.log, 13:30:13-13:30:40), one ``[member mask][field mask][fields]`` block:

    01 01 <f32>            bit 0: stamina amount (0..100 for a player), at ~60 Hz while it changes
    01 08 <f32>            bit 3: a countdown 1.0 -> 0.0 in 0.05 steps before regeneration starts
    01 0c <f32> <f32>      bits 2, 3: a second countdown 2.0 -> 1.0 (after the bar hit 0), then bit 3
    01 09 <f32> <f32>      bits 0, 3 together: 55.0 and 1.0 right after the dodge cost
    01 0d <f32> <f32> <f32> bits 0, 2, 3: 0.0, 2.0, 1.0 when the bar was emptied
    01 20 <f32>            bit 5 alone: 1.0, 1.2, 1.25 (a multiplier; regeneration rate is the guess, unverified)
    01 3f <f32> x 6        the full state when the entity enters scope: 100, 100, 0, 0, 1.0, 1.0

Every field is a big-endian float32 and they come in bit order; bit 1 is the maximum (100 next to a
100 amount in the full state). Bits above 5 were never set, so a payload carrying them is not decoded.
"""
import struct

FIELDS = {0: "stamina", 1: "stamina_max", 2: "winded_s", 3: "regen_delay_s", 4: "field4", 5: "field5"}


def parse_stamina(payload: bytes):
    """Return the decoded fields of one payload, or an empty dict for a shape not seen."""
    out = {}
    if len(payload) < 2 or payload[0] != 0x01:
        return out
    field_mask = payload[1]
    if field_mask & ~0x3F:
        return out
    index = 2
    for bit in range(6):
        if not field_mask >> bit & 1:
            continue
        if index + 4 > len(payload):
            return {}
        out[FIELDS[bit]] = round(struct.unpack(">f", payload[index:index + 4])[0], 3)
        index += 4
    return out if index == len(payload) else {}


def check():
    assert parse_stamina(bytes.fromhex("01014262aa7f")) == {"stamina": 56.667}
    assert parse_stamina(bytes.fromhex("01083f733333")) == {"regen_delay_s": 0.95}
    assert parse_stamina(bytes.fromhex("0109425c00003f800000")) == {"stamina": 55.0, "regen_delay_s": 1.0}
    assert parse_stamina(bytes.fromhex("010d00000000400000003f800000")) == {"stamina": 0.0, "winded_s": 2.0, "regen_delay_s": 1.0}
    assert parse_stamina(bytes.fromhex("010c3ff9999a3f733333")) == {"winded_s": 1.95, "regen_delay_s": 0.95}
    assert parse_stamina(bytes.fromhex("013f42c8000042c8000000000000000000003f8000003f800000")) == {
        "stamina": 100.0, "stamina_max": 100.0, "winded_s": 0.0, "regen_delay_s": 0.0, "field4": 1.0, "field5": 1.0}
    assert parse_stamina(bytes.fromhex("0140deadbeef")) == {}       # bit 6: never seen, not guessed
    assert parse_stamina(bytes.fromhex("01014262aa7f00")) == {}     # a trailing byte the mask does not cover
    print("decode_stamina check ok")


if __name__ == "__main__":
    check()
