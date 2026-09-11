"""Plain-assert round-trip checks for the ALC encoder."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from decode_alc_state import (  # noqa: E402
    GROUP0_READER_TABLE,
    GROUP1_READER_TABLE,
    decode_record_payload,
    iter_records,
    read_mask_varint,
    read_prefix_varint,
)
from decode_in_bodies import channel_stream, iter_frames  # noqa: E402
from decode_join import ledger_items, log_items  # noqa: E402
from encode_alc_state import (  # noqa: E402
    encode_mask_varint,
    encode_prefix_varint,
    encode_record,
    encode_record_payload,
)

LOGS = tuple(
    ROOT / "Tools/nw_capture/logs" / name
    for name in (
        "20260911-111610_join2.log",
        "20260911-112222_join3.log",
        "20260911-112506_joinwalk.log",
    )
)
LEDGER = ROOT / "Tools/nw_capture/captures/proton_20260910_174014-alcact/dtls/ledger.bin"


def _field_groups(group_mask, fields):
    groups = {0: [], 1: []}
    for field in fields:
        bit, name, chunk, _value = field
        matches = [
            group
            for group, table in ((0, GROUP0_READER_TABLE), (1, GROUP1_READER_TABLE))
            if group_mask & (1 << group) and table.get(bit, (None,))[0] == name
        ]
        assert len(matches) == 1, (group_mask, field, matches)
        groups[matches[0]].append(field)
    for fields_in_group in groups.values():
        fields_in_group.sort(key=lambda field: field[0])
    return groups


def _check_payload_varints(payload, fields):
    groups = _field_groups(payload[0], fields)
    cursor = 1
    mask_count = prefix_count = 0
    mask_longer = prefix_longer = 0
    for group in (0, 1):
        if not payload[0] & (1 << group):
            continue
        mask, size = read_mask_varint(payload, cursor)
        assert mask is not None and size > 0
        raw_mask = payload[cursor:cursor + size]
        encoded_mask = encode_mask_varint(mask)
        if len(encoded_mask) < size:
            mask_longer += 1
        assert encoded_mask == raw_mask
        mask_count += 1
        cursor += size
        table = GROUP0_READER_TABLE if group == 0 else GROUP1_READER_TABLE
        for bit, _name, chunk, _value in groups[group]:
            reader = table[bit][1]
            if reader == "prefixVarint":
                value, prefix_size = read_prefix_varint(chunk, 0)
                assert value is not None and prefix_size == len(chunk)
                encoded = encode_prefix_varint(value)
                if len(encoded) < len(chunk):
                    prefix_longer += 1
                assert encoded == chunk or len(encoded) < len(chunk)
                prefix_count += 1
            elif reader in ("bytes33", "bytes177"):
                value, prefix_size = read_prefix_varint(chunk, 0)
                assert value is not None and prefix_size > 0
                encoded = encode_prefix_varint(value)
                raw_prefix = chunk[:prefix_size]
                if len(encoded) < prefix_size:
                    prefix_longer += 1
                assert encoded == raw_prefix or len(encoded) < prefix_size
                prefix_count += 1
            cursor += len(chunk)
    assert cursor == len(payload), (cursor, len(payload), payload.hex())
    return mask_count, prefix_count, mask_longer, prefix_longer


def _check_varint_boundaries():
    mask_values = [
        0,
        (1 << 7) - 1,
        1 << 7,
        (1 << 14) - 1,
        1 << 14,
        (1 << 21) - 1,
        1 << 21,
        (1 << 28) - 1,
        1 << 28,
        (1 << 35) - 1,
        1 << 35,
        (1 << 42) - 1,
        1 << 42,
        (1 << 49) - 1,
        1 << 49,
        (1 << 56) - 1,
        1 << 56,
        (1 << 64) - 1,
    ]
    for value in mask_values:
        encoded = encode_mask_varint(value)
        assert read_mask_varint(encoded, 0) == (value, len(encoded))
    prefix_values = [
        0,
        (1 << 7) - 1,
        1 << 7,
        (1 << 14) - 1,
        1 << 14,
        (1 << 21) - 1,
        1 << 21,
        (1 << 28) - 1,
        1 << 28,
        (1 << 35) - 1,
    ]
    for value in prefix_values:
        encoded = encode_prefix_varint(value)
        assert read_prefix_varint(encoded, 0) == (value, len(encoded))
    assert encode_mask_varint(0x04000003) == bytes.fromhex("e3000040")
    assert encode_mask_varint(0x1C000403) == bytes.fromhex("f380008003")
    assert encode_prefix_varint(1873) == bytes.fromhex("911d")
    assert encode_prefix_varint(0x40087) == bytes.fromhex("c72004")


def _check_join_payloads():
    chunks = exact = identical = inexact = 0
    mask_count = prefix_count = 0
    mask_longer = prefix_longer = 0
    for path in LOGS:
        for item in log_items(path.read_text(errors="ignore").splitlines()):
            if item[3] != 11:
                continue
            chunks += 1
            payload = bytes.fromhex(item[6])
            assert item[5] == len(payload), (path, item)
            fields, used = decode_record_payload(payload)
            if fields is None or used != len(payload):
                inexact += 1
                continue
            exact += 1
            encoded = encode_record_payload(payload[0], fields)
            assert encoded == payload, (path, item, encoded.hex(), payload.hex())
            identical += 1
            masks, prefixes, masks_long, prefixes_long = _check_payload_varints(payload, fields)
            mask_count += masks
            prefix_count += prefixes
            mask_longer += masks_long
            prefix_longer += prefixes_long
    assert exact == identical
    return chunks, identical, inexact, mask_count, prefix_count, mask_longer, prefix_longer


def _check_ledger_headers():
    rows = list(ledger_items(LEDGER))
    stream = channel_stream(str(LEDGER))
    records = row_index = large_values = 0
    divergences = []
    for _offset, _counter, body, _trailer in iter_frames(stream):
        for start, v1, v2, _group_mask, payload_offset, _fields in iter_records(body):
            payload_fields, payload_size = decode_record_payload(body, payload_offset)
            assert payload_fields is not None and payload_size > 0
            payload = body[payload_offset:payload_offset + payload_size]
            raw = body[start:payload_offset + payload_size]
            assert encode_record(v1, v2, 11, payload) == raw
            assert row_index < len(rows)
            row = rows[row_index]
            assert row[1] == v1 and row[2] == v2 and row[5] == payload_size
            assert row[6] == payload.hex()
            row_index += 1
            records += 1

            v1_mask, v1_mask_size = read_mask_varint(body, start)
            v1_prefix, v1_prefix_size = read_prefix_varint(body, start)
            assert v1_mask == v1 and v1_prefix == v1
            if v1 >= 0x80:
                large_values += 1
            if v1_mask != v1_prefix or v1_mask_size != v1_prefix_size:
                divergences.append(("V1", v1, body[start:start + max(v1_mask_size, v1_prefix_size)].hex()))

            v2_start = start + v1_mask_size + 1
            v2_mask, v2_mask_size = read_mask_varint(body, v2_start)
            v2_prefix, v2_prefix_size = read_prefix_varint(body, v2_start)
            assert v2_mask == v2 and v2_prefix == v2
            if v2 >= 0x80:
                large_values += 1
            if v2_mask != v2_prefix or v2_mask_size != v2_prefix_size:
                divergences.append(("V2", v2, body[v2_start:v2_start + max(v2_mask_size, v2_prefix_size)].hex()))

    assert row_index == len(rows)
    assert not [entry for entry in divergences if entry[1] >= 0x80], divergences
    return records, large_values, divergences


def check():
    _check_varint_boundaries()
    (chunks, identical, inexact, mask_count, prefix_count, mask_longer,
     prefix_longer) = _check_join_payloads()
    ledger_records, large_values, divergences = _check_ledger_headers()
    assert chunks == identical + inexact
    print(f"join ALC chunks tested: {chunks}")
    print(f"join ALC payloads identical: {identical}")
    print(f"join ALC payloads inexact: {inexact}")
    print(f"payload mask varints tested: {mask_count}")
    print(f"payload prefix varints tested: {prefix_count}")
    print(f"longer-than-minimal mask varints: {mask_longer}")
    print(f"longer-than-minimal prefix varints: {prefix_longer}")
    print(f"ledger ALC record headers round-tripped: {ledger_records}")
    print(f"ledger V1/V2 values >= 0x80: {large_values}")
    print(f"V1/V2 mask-prefix divergences >= 0x80: {len(divergences)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(check())
