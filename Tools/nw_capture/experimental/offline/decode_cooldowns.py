"""CooldownTimersComponentReplicatedState (typeIndex 2932): ability and consumable cooldowns.

Delta shape, read from the player's chunks (logs/20260911-130958_live.log, 13:11-13:28), one entry
per member, the member bit being the cooldown slot:

    01                  a leading byte, always 01 (a group mask, as in ALC)
    [member mask]       then per set bit, the bit being the slot:
      01                field mask, only bit 0 seen
      01                one entry
      <u32 BE>          cooldown id (the same id came back with the same duration: 9d35d4b6 = 20.92 s twice)
      01                one sub-entry
      <prefix varint>   a revision, grows over the session (2464 -> 2504 -> 10046 -> ...)
      <u64 BE>          expiry, microseconds since 2000-01-01 UTC
      <u64 BE>          start, same unit; it sat 40 ms before the arrival time of the chunk

The full state the entity brings into scope (6 KB, member mask 0x77) has another shape and is not
decoded here; only deltas are, and anything else returns an empty list.
"""
import datetime
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from decode_alc_state import read_prefix_varint  # noqa: E402

EPOCH_2000 = datetime.datetime(2000, 1, 1, tzinfo=datetime.timezone.utc).timestamp()


def server_time_to_unix(microseconds: int) -> float:
    return EPOCH_2000 + microseconds / 1e6


def parse_cooldowns(payload: bytes):
    """Return [{"slot", "id", "start", "expiry"}] with unix seconds, or [] for a shape not seen."""
    if len(payload) < 2 or payload[0] != 0x01:
        return []
    member_mask = payload[1]
    index = 2
    out = []
    for slot in range(8):
        if not member_mask >> slot & 1:
            continue
        if payload[index:index + 2] != b"\x01\x01" or len(payload) < index + 7:
            return []
        cooldown_id = struct.unpack(">I", payload[index + 2:index + 6])[0]
        if payload[index + 6] != 0x01:
            return []
        _revision, size = read_prefix_varint(payload, index + 7)
        if size == 0 or len(payload) < index + 7 + size + 16:
            return []
        expiry, start = struct.unpack(">QQ", payload[index + 7 + size:index + 7 + size + 16])
        if not start <= expiry <= start + 3600 * 1_000_000:
            return []
        out.append({"slot": slot, "id": f"{cooldown_id:08x}",
                    "start": server_time_to_unix(start), "expiry": server_time_to_unix(expiry)})
        index += 7 + size + 16
    return out if index == len(payload) else []


def check():
    one = parse_cooldowns(bytes.fromhex("010101011b0fa51101a0260002fe31ed13a78b0002fe31eba6f914"))
    assert len(one) == 1 and one[0]["slot"] == 0 and one[0]["id"] == "1b0fa511", one
    assert abs(one[0]["expiry"] - one[0]["start"] - 23.9) < 0.01, one
    assert datetime.datetime.fromtimestamp(one[0]["start"], datetime.timezone.utc).strftime("%Y-%m-%d %H:%M") == "2026-09-11 11:11"
    two = parse_cooldowns(bytes.fromhex("010301011b0fa51101b2260002fe31ed01580c0002fe31eba6f914"
                                        "0101473ac2ed01b2260002fe31ec5eb1330002fe31ebb481ec"))
    assert [c["slot"] for c in two] == [0, 1] and two[1]["id"] == "473ac2ed", two
    three_byte = parse_cooldowns(bytes.fromhex("010101019d35d4b601d6a6020002fe322648932e0002fe3225096a36"))
    assert len(three_byte) == 1 and abs(three_byte[0]["expiry"] - three_byte[0]["start"] - 20.92) < 0.01
    assert parse_cooldowns(bytes.fromhex("0177000100")) == []          # the full-state shape is not guessed
    assert parse_cooldowns(bytes.fromhex("010101011b0fa51101a0260002fe31ed13a78b0002fe31eba6f91400")) == []
    print("decode_cooldowns check ok")


if __name__ == "__main__":
    check()
