"""Decode the ALCReplicatedState field payload from a capture ledger.

Wire layout (Ghidra and live trace evidence from 2026-09-10;
see docs/Network/alc-protocol-reference.md):

    body    := record+
    record  := [V1 mask-varint][0x01][V2 mask-varint][0x0b][group mask][payload]
    payload := for each set group: [field mask mask-varint][group fields]

The group mask is one byte: bit 0 enables group 0 and bit 1 enables group 1.
The two groups have separate entry vectors.  The runtime reader map below is the
map observed for group 0; it is deliberately not substituted with the global
name-order table from the static schema.
"""
import argparse
import struct
import sys
from pathlib import Path

# The field-mask reader accepts up to nine bytes.  The ALC dispatcher clips its
# result to 54 bits before indexing the group entry vector.
MAX_MASK_BYTES = 9
MAX_FIELD_BITS = 54
FIELD_MASK_LIMIT = (1 << MAX_FIELD_BITS) - 1
MAX_PREFIX_BYTES = 5


def _runtime_entries():
    """Return (name, reader) entries for the observed group-0 vector."""
    return {
        0: ("idRel", "u8"), 1: ("timeOffsetRel", "u8"),
        2: ("slayerSeqTimeRel", "u8Float"), 3: ("slayerSeqTimeAbs", "halfFloat"),
        4: ("slayerSeqTimeRel", "u8Float"), 5: ("slayerSeqTimeAbs", "halfFloat"),
        6: ("slayerSeqTimeRel", "u8Float"), 7: ("slayerSeqTimeAbs", "halfFloat"),
        8: ("group0.bit8", "halfFloat"), 9: ("group0.bit9", "halfFloat"),
        10: ("worldPosRel", "worldPosRel"), 11: ("rotation", "rotationQuaternion"),
        12: ("lookDir", "lookDirQuaternion"), 13: ("slayerStateId", "prefixVarint"),
        14: ("slayerStateIdStarted", "u16"), 15: ("slayerSequenceId", "prefixVarint"),
        16: ("slayerStateId", "prefixVarint"), 17: ("slayerStateIdStarted", "u16"),
        18: ("slayerSequenceId", "prefixVarint"), 19: ("slayerStateId", "prefixVarint"),
        20: ("slayerStateIdStarted", "u16"), 21: ("slayerSequenceId", "prefixVarint"),
        22: ("slayerStateId", "prefixVarint"), 23: ("slayerStateIdStarted", "u16"),
        24: ("slayerSequenceId", "prefixVarint"), 25: ("idAbs", "u8High"),
        26: ("timeOffsetAbs", "u8High"), 27: ("worldPosAbs", "worldPosAbs"),
        28: ("scopeTimeBlob0Data0", "u8State"), 29: ("scopeTimeBlobEx", "bytes33"),
        30: ("scopeTimeBlob1Data0", "u8State"), 31: ("teleportAndMigrationId", "u8State"),
        32: ("scopeData", "prefixVarint"), 33: ("scopeInfoBlob", "bytes177"),
        34: ("globalFragTags", "bytes12"), 35: ("group0.bit35", "u32"),
        36: ("group0.bit36", "halfFloat"), 37: ("group0.bit37", "halfFloat"),
        38: ("group0.bit38", "u8State"), 39: ("group0.bit39", "halfFloat"),
        40: ("group0.bit40", "u64"), 41: ("group0.bit41", "u8State"),
        42: ("group0.bit42", "u8State"), 43: ("group0.bit43", "u8State"),
        44: ("group0.bit44", "u8State"), 45: ("group0.bit45", "u8State"),
        46: ("group0.bit46", "prefixVarint"), 47: ("group0.bit47", "u8State"),
        48: ("group0.bit48", "prefixVarint"), 49: ("group0.bit49", "u8State"),
        50: ("group0.bit50", "u8State"), 51: ("group0.bit51", "u8State"),
        52: ("group0.bit52", "u8State"), 53: ("group0.bit53", "u32"),
    }


# This is the only group-1 entry observed in the supplied trace.  Unknown
# group-1 bits are rejected instead of being decoded with group 0's layout.
GROUP0_READER_TABLE = _runtime_entries()
GROUP1_READER_TABLE = {0: ("group1.bit0", "u8State")}


def _reader_width(reader):
    return {
        "u8": 1, "u8Float": 1, "u8High": 1, "u8State": 1,
        "u16": 2, "u32": 4, "u64": 8, "halfFloat": 2,
        "worldPosRel": 3, "worldPosAbs": 10,
        "bytes12": 12, "prefixVarint": "v", "bytes33": "b33",
        "bytes177": "b177", "rotationQuaternion": "q", "lookDirQuaternion": "q",
    }[reader]


# Compatibility view for callers that used the old single-group decoder.
FIELD_TABLE = {
    bit: (name, _reader_width(reader))
    for bit, (name, reader) in GROUP0_READER_TABLE.items()
}
GROUP_FIELD_TABLES = {
    0: FIELD_TABLE,
    1: {bit: (name, _reader_width(reader))
        for bit, (name, reader) in GROUP1_READER_TABLE.items()},
}


def _leading_ones(byte):
    count = 0
    for shift in range(7, -1, -1):
        if byte >> shift & 1:
            count += 1
        else:
            break
    return count


def read_mask_varint(data, offset):
    """FUN_14087b770. Return the un-clipped (value, byte count)."""
    if offset < 0 or offset >= len(data):
        return None, 0
    first = data[offset]
    if first < 0x80:
        return first, 1

    size = _leading_ones(first) + 1
    if size > MAX_MASK_BYTES or offset + size > len(data):
        return None, 0
    extra = int.from_bytes(data[offset + 1:offset + size], "little")
    # For ff + eight bytes the first byte contributes no value bits.  The
    # preceding branches are the same formula with a positive shift.
    shift = max(8 - size, 0)
    first_mask = (1 << (8 - size)) - 1 if size < 8 else 0
    return (extra << shift) | (first & first_mask), size


def read_prefix_varint(data, offset):
    """Read the 1..5-byte prefix varint used by field reader 0x142a42e60."""
    if offset < 0 or offset >= len(data):
        return None, 0
    first = data[offset]
    if first < 0x80:
        return first, 1
    if first < 0xC0:
        if offset + 1 >= len(data):
            return None, 0
        return ((data[offset + 1] << 6) | (first & 0x3F)), 2
    if first < 0xE0:
        if offset + 2 >= len(data):
            return None, 0
        return (((data[offset + 1] << 8 | data[offset + 2]) << 5)
                | (first & 0x1F)), 3
    if first < 0xF0:
        if offset + 3 >= len(data):
            return None, 0
        value = (data[offset + 1] << 16 | data[offset + 2] << 8
                 | data[offset + 3])
        return ((value << 4) | (first & 0x0F)), 4
    if offset + 4 >= len(data):
        return None, 0
    value = (data[offset + 1] << 24 | data[offset + 2] << 16
             | data[offset + 3] << 8 | data[offset + 4])
    return ((value << 3) | (first & 0x07)), 5


def read_quaternion(data, offset):
    """FUN_14087a8d0: control byte plus absent components, at most three bytes."""
    if offset < 0 or offset >= len(data):
        return None, 0
    control = data[offset]
    count = 3 if (control & 2) == 0 else 2
    for bit in (4, 8):
        if control & bit:
            count -= 1
    if (control & 0x10) and count:
        count -= 1
    count = max(count, 0)
    size = 1 + count
    if offset + size > len(data):
        return None, 0
    return data[offset:offset + size], size


def _read_field(data, offset, reader):
    width = _reader_width(reader)
    if isinstance(width, int):
        end = offset + width
        if offset < 0 or end > len(data):
            return None, 0
        return data[offset:end], width
    if reader in ("rotationQuaternion", "lookDirQuaternion"):
        return read_quaternion(data, offset)
    if reader == "prefixVarint":
        value, size = read_prefix_varint(data, offset)
        if value is None:
            return None, 0
        return data[offset:offset + size], size
    if reader in ("bytes33", "bytes177"):
        count, prefix_size = read_prefix_varint(data, offset)
        limit = 33 if reader == "bytes33" else 177
        if count is None or count > limit:
            return None, 0
        end = offset + prefix_size + count
        if end > len(data):
            return None, 0
        return data[offset:end], prefix_size + count
    raise ValueError(f"unsupported ALC reader {reader}")


def decode_group_payload(data, offset=0, group=0):
    """Decode one group's field-mask payload.

    Return ``(fields, bytes_consumed)``.  Each field is
    ``(bit, name, raw, interpreted_value)``.  The offset points at the field
    mask, not at the record's group-mask byte.
    """
    table = GROUP_FIELD_TABLES.get(group)
    if table is None:
        return None, 0
    mask, mask_size = read_mask_varint(data, offset)
    if mask is None:
        return None, 0
    mask &= FIELD_MASK_LIMIT
    cursor = offset + mask_size
    fields = []
    for bit in range(MAX_FIELD_BITS):
        if not (mask >> bit) & 1:
            continue
        entry = table.get(bit)
        if entry is None:
            return None, 0
        name, width = entry
        reader = GROUP0_READER_TABLE[bit][1] if group == 0 else GROUP1_READER_TABLE[bit][1]
        chunk, used = _read_field(data, cursor, reader)
        if chunk is None or used == 0:
            return None, 0
        fields.append((bit, name, chunk, interpret(name, chunk)))
        cursor += used
    return fields, cursor - offset


def decode_payload(data, offset=0, group=0):
    """Compatibility wrapper for a field-mask payload (group 0 by default)."""
    return decode_group_payload(data, offset, group)


def decode_record_payload(data, offset=0):
    """Decode the group mask and all enabled group payloads."""
    if offset < 0 or offset >= len(data):
        return None, 0
    group_mask = data[offset]
    if group_mask not in (1, 3):
        return None, 0
    cursor = offset + 1
    fields = []
    for group in (0, 1):
        if not (group_mask >> group) & 1:
            continue
        group_fields, used = decode_group_payload(data, cursor, group)
        if group_fields is None or used == 0:
            return None, 0
        fields.extend(group_fields)
        cursor += used
    return fields, cursor - offset


def interpret(name, chunk):
    """Best-effort value for fields whose wire representation is established."""
    if name == "worldPosAbs" and len(chunk) == 10:
        east, north = struct.unpack(">ff", chunk[:8])
        quantised = struct.unpack(">H", chunk[8:])[0]
        return {"east": round(east, 3), "north": round(north, 3),
                "elevation": round(quantised / 65535 * 1100 - 100, 3)}
    if name in ("wpnaccrystance", "wpnaccrymvmnt", "slayerSeqTimeAbs") and len(chunk) == 2:
        return round(struct.unpack(">e", chunk)[0], 4)
    if name == "worldPosRel" and len(chunk) == 3:
        return list(chunk) if chunk != b"\xff\xff\xff" else "no update"
    if name == "quantization" and len(chunk) == 4:
        return struct.unpack("<I", chunk)[0]
    if name == "aiAngleToDesiredFacing" and len(chunk) == 4:
        return struct.unpack(">I", chunk)[0]
    if name == "timeAnchor" and len(chunk) == 8:
        return struct.unpack("<Q", chunk)[0]
    return None


def iter_records(body):
    """Yield ``(offset, v1, v2, group_mask, payload offset, fields)``.

    A body holds records of many types; iteration stops at the first record
    that is not ALC or whose group payload cannot be measured exactly.
    """
    offset = 0
    while offset < len(body):
        start = offset
        v1, n1 = read_mask_varint(body, offset)
        if n1 == 0 or offset + n1 + 1 >= len(body) or body[offset + n1] != 0x01:
            return
        offset += n1 + 1
        v2, n2 = read_mask_varint(body, offset)
        if (n2 == 0 or offset + n2 + 1 >= len(body)
                or body[offset + n2] != 0x0B):
            return
        offset += n2 + 1
        group_mask = body[offset]
        fields, used = decode_record_payload(body, offset)
        if fields is None or used == 0:
            return
        yield start, v1, v2, group_mask, offset, fields
        offset += used


def main(argv=None):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from decode_in_bodies import channel_stream, iter_frames

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--limit", type=int, default=3, help="records printed in full")
    parser.add_argument("--field", help="only records carrying this field name")
    args = parser.parse_args(argv)

    shown = records = 0
    for offset, counter, body, _trailer in iter_frames(channel_stream(str(args.ledger))):
        for _start, v1, v2, group_mask, payload_offset, fields in iter_records(body):
            records += 1
            if args.field and args.field not in [name for _, name, _, _ in fields]:
                continue
            if shown >= args.limit:
                continue
            shown += 1
            total = sum(len(chunk) for _, _, chunk, _ in fields)
            print(f"frame@{offset} counter={counter} V1={v1} V2={v2} "
                  f"groupMask={group_mask} payload@{payload_offset} "
                  f"{total}B  {len(fields)} fields")
            for bit, name, chunk, value in fields:
                extra = f"  -> {value}" if value is not None else ""
                print(f"    bit {bit:2d} {name:<24} {len(chunk):2d}B {chunk.hex()}{extra}")
            print()
    print(f"record ALC decodificati in questa cattura: {records}")


if __name__ == "__main__":
    main()
