"""MountComponentReplicatedState (typeIndex 5620): mounted or not, for the player and for others.

Read from the player's chunks around a driven mount (14:23:15) and dismount (14:27:59) and from the
remote players' deltas in logs/20260911-134254_live3.log.

Owner (member mask 02, member 1), fields in bit order:
    bit 0  u8        1 on mount, 0 on dismount
    bit 1  u64 BE    dismount time, nanoseconds since 1970
    bit 2  u8        1 / 0, toggled twice while riding (unknown, ignored)
    bit 4  u8 + u64  1 + a time in ns since 1970 (5 s after the chunk arrived) on mount, 0 + 0 on dismount
    bit 6  f32 BE    mount stamina, 100 -> 97 -> 100 while galloping
    bit 7  unknown width (5 or 9 bytes seen): parsing stops there
Remote (member mask 0c or 08, members 2 and 3):
    member 2 field 01  u32 BE mount type id, 0 when dismounted (e4fdfda0 on two different players)
    member 3 field 01  u8 state: 01 summoning, 05 riding, 04 mount out but owner on foot (walking speeds);
                       field 03 adds a u32 (colours). Riding = state in RIDING_STATES, not id != 0
"""
import struct

RIDING_STATES = (1, 3, 5, 9)     # 1 summoning/mounting, 5 riding, 3 and 9 seen at riding speed; 4 = mount out, owner on foot


def parse_mount(payload: bytes):
    """Return any of mounted, mount_stamina, mount_id, mount_state; {} for a shape not seen."""
    if len(payload) < 2:
        return {}
    member_mask = payload[0]
    out = {}
    index = 1
    if member_mask == 0x02:
        field_mask = payload[1]
        index = 2
        widths = {0: 1, 1: 8, 2: 1, 4: 9, 6: 4}
        for bit in range(8):
            if not field_mask >> bit & 1:
                continue
            if bit not in widths:
                return out                     # bit 3, 5, 7: width not established
            chunk = payload[index:index + widths[bit]]
            if len(chunk) != widths[bit]:
                return {}
            index += widths[bit]
            if bit == 0:
                out["mounted"] = chunk[0] == 1
            elif bit == 4:
                out["mounted"] = chunk[0] == 1
                out["mount_since"] = struct.unpack(">Q", chunk[1:])[0] / 1e9 if chunk[0] == 1 else None
            elif bit == 6:
                out["mount_stamina"] = round(struct.unpack(">f", chunk)[0], 1)
        return out
    if member_mask & ~0x0C or member_mask == 0:
        return {}
    if member_mask & 0x04:
        if payload[index] != 0x01 or len(payload) < index + 5:
            return {}
        mount_id = struct.unpack(">I", payload[index + 1:index + 5])[0]
        out["mount_id"] = f"{mount_id:08x}"
        if mount_id == 0:
            out["mounted"] = False
        index += 5
    if member_mask & 0x08:
        if len(payload) < index + 2:
            return {}
        field_mask = payload[index]
        if field_mask & ~0x03:
            return {}
        out["mount_state"] = payload[index + 1]
        # id set + state 4 moved at walking speed (median 0, p90 4.5 u/s over 4,995 samples); states 1 and
        # 5 at 8.6 / 6.0 median, p90 11.4: a mount can be out while its owner stands on foot (state 4)
        out["mounted"] = out["mount_state"] in RIDING_STATES
        index += 2
        if field_mask & 0x02:
            index += 4
    return out if index == len(payload) else {}


def check():
    mount = parse_mount(bytes.fromhex("02100118d443b5eded1434"))
    # the chunk arrived at 14:23:15.68 CEST = 1789129395.7; the stamp reads 5 s later, so it is a time
    # near the mount, not proven to be the mount instant
    assert mount["mounted"] is True and abs(mount["mount_since"] - 1789129395.7) < 10.0, mount
    dismount = parse_mount(bytes.fromhex("02130018d443f7212ec4c8000000000000000000"))
    assert dismount["mounted"] is False and dismount["mount_since"] is None, dismount
    assert parse_mount(bytes.fromhex("024042c6aaab")) == {"mount_stamina": 99.3}
    assert parse_mount(bytes.fromhex("0281010c4120000041a00000")) == {"mounted": True}   # bit 7 stops the walk
    assert parse_mount(bytes.fromhex("020401")) == {}                                     # bit 2 alone: nothing to say
    riding = parse_mount(bytes.fromhex("0c01e4fdfda0030500000000"))
    assert riding == {"mount_id": "e4fdfda0", "mount_state": 5, "mounted": True}, riding
    assert parse_mount(bytes.fromhex("0c0100000000030400000000"))["mounted"] is False
    assert parse_mount(bytes.fromhex("0c01e4fdfda0030400000000"))["mounted"] is False   # mount out, owner on foot
    assert parse_mount(bytes.fromhex("080105")) == {"mount_state": 5, "mounted": True}
    assert parse_mount(bytes.fromhex("0c01e4fdfda003050000000000")) == {}
    print("decode_mount check ok")


if __name__ == "__main__":
    check()
