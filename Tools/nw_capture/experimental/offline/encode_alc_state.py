"""Encode the ALC record framing decoded by decode_alc_state.py."""
import sys
from decode_alc_state import (  # noqa: E402
    GROUP0_READER_TABLE,
    GROUP1_READER_TABLE,
)

MAX_MASK_VALUE = (1 << 64) - 1
MAX_PREFIX_VALUE = (1 << 35) - 1

# Real-log checks found longer-than-minimal prefix encodings, but no mask ones;
# the writers remain shortest-first and payload chunks preserve those raw bytes.


def _integer(value, name, maximum):
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer")
    if value < 0 or value > maximum:
        raise ValueError(f"{name} must be between 0 and {maximum}")
    return value


def encode_mask_varint(value):
    """Encode FUN_14087b770's 1..9-byte mask varint, shortest first."""
    value = _integer(value, "mask value", MAX_MASK_VALUE)
    limits = (1 << 7, 1 << 14, 1 << 21, 1 << 28, 1 << 35,
              1 << 42, 1 << 49, 1 << 56, 1 << 64)
    for size, limit in enumerate(limits, 1):
        if value < limit:
            break
    payload_bits = max(8 - size, 0)
    first_prefix = ((1 << (size - 1)) - 1) << (9 - size)
    first = first_prefix | (value & ((1 << payload_bits) - 1))
    extra = value >> payload_bits
    return bytes([first]) + extra.to_bytes(size - 1, "little")


def encode_prefix_varint(value):
    """Encode FUN_14087b5c0's 1..5-byte prefix varint, shortest first."""
    value = _integer(value, "prefix value", MAX_PREFIX_VALUE)
    limits = (1 << 7, 1 << 14, 1 << 21, 1 << 28, 1 << 35)
    for size, limit in enumerate(limits, 1):
        if value < limit:
            break
    payload_bits = 8 - size
    first_prefix = ((1 << (size - 1)) - 1) << (9 - size)
    first = first_prefix | (value & ((1 << payload_bits) - 1))
    extra = value >> payload_bits
    return bytes([first]) + extra.to_bytes(size - 1, "big")


def encode_record_payload(group_mask, fields):
    """Rebuild a record payload from decoded fields and its outer group mask."""
    group_mask = _integer(group_mask, "group mask", 0xFF)
    if group_mask not in (1, 3):
        raise ValueError("ALC group mask must be 1 or 3")

    groups = {0: [], 1: []}
    seen = {0: set(), 1: set()}
    for bit, name, chunk, _value in fields:
        if type(bit) is not int or bit < 0 or bit >= 54:
            raise ValueError(f"invalid ALC field bit: {bit!r}")
        if not isinstance(name, str):
            raise TypeError("ALC field name must be a string")
        if not isinstance(chunk, (bytes, bytearray, memoryview)):
            raise TypeError("ALC field chunk must be bytes-like")
        matches = []
        for group, table in ((0, GROUP0_READER_TABLE), (1, GROUP1_READER_TABLE)):
            entry = table.get(bit)
            if group_mask & (1 << group) and entry is not None and entry[0] == name:
                matches.append(group)
        if len(matches) != 1:
            raise ValueError(f"field does not identify one enabled ALC group: {(bit, name)!r}")
        group = matches[0]
        if bit in seen[group]:
            raise ValueError(f"duplicate ALC field bit {bit} in group {group}")
        seen[group].add(bit)
        groups[group].append((bit, bytes(chunk)))

    output = bytearray([group_mask])
    for group in (0, 1):
        if not group_mask & (1 << group):
            continue
        group_fields = sorted(groups[group], key=lambda item: item[0])
        field_mask = 0
        for bit, _chunk in group_fields:
            field_mask |= 1 << bit
        output.extend(encode_mask_varint(field_mask))
        for _bit, chunk in group_fields:
            output.extend(chunk)
    return bytes(output)


def encode_record(v1, v2, type_index, payload):
    """Encode one record with its one-chunk header and payload."""
    if not isinstance(payload, (bytes, bytearray, memoryview)):
        raise TypeError("record payload must be bytes-like")
    return (encode_prefix_varint(v1) + b"\x01" + encode_prefix_varint(v2)
            + encode_prefix_varint(type_index) + bytes(payload))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv != ["--check"]:
        raise SystemExit("usage: encode_alc_state.py --check")
    from test_encode_alc_state import check
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
