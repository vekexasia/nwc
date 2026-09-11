#!/usr/bin/env python3
"""Encode and verify the inbound frame and record layers."""
import collections
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from decode_alc_state import (  # noqa: E402
    decode_record_payload,
    iter_records,
    read_mask_varint,
    read_prefix_varint as read_record_prefix_varint,
)
from decode_in_bodies import (  # noqa: E402
    channel_stream,
    iter_frames,
    read_prefix_varint as read_frame_prefix_varint,
)
from encode_alc_state import encode_prefix_varint, encode_record  # noqa: E402

MARKER = b"\x00\x01\x08\x01"
FRAME_HEADER_SIZE = 14
MAX_U32 = (1 << 32) - 1
CAPTURES = (
    ROOT / "Tools/nw_capture/captures/proton_20260910_174014-alcact/dtls/ledger.bin",
    ROOT / "Tools/nw_capture/captures/proton_20260911_082212-actions2/dtls/ledger.bin",
)


def _integer(value, name, maximum):
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer")
    if value < 0 or value > maximum:
        raise ValueError(f"{name} must be between 0 and {maximum}")
    return value


def _bytes(value, name):
    if not isinstance(value, (bytes, bytearray, memoryview)):
        raise TypeError(f"{name} must be bytes-like")
    return bytes(value)


def encode_frame(counter, flags4, body, trailer_value):
    """Encode one frame from its counter, four message bytes, body, and trailer."""
    counter = _integer(counter, "counter", MAX_U32)
    flags4 = _bytes(flags4, "flags4")
    if len(flags4) != 4:
        raise ValueError("flags4 must contain exactly 4 bytes")
    body = _bytes(body, "body")
    if len(body) > 0xFFFF:
        raise ValueError("body must fit in a u16 length")
    trailer_value = _integer(trailer_value, "trailer value", (1 << 35) - 1)
    return (MARKER + struct.pack("<I", counter) + flags4
            + struct.pack(">H", len(body)) + body
            + encode_prefix_varint(trailer_value))


def _difference(frame_offset, original, encoded, stream_base=None):
    if stream_base is None:
        stream_base = frame_offset
    for index in range(min(len(original), len(encoded))):
        if original[index] != encoded[index]:
            start = max(0, index - 8)
            end = min(max(len(original), len(encoded)), index + 8)
            return {
                "frame_offset": frame_offset,
                "stream_offset": stream_base + index,
                "original": original[start:end].hex(),
                "encoded": encoded[start:end].hex(),
            }
    if len(original) != len(encoded):
        index = min(len(original), len(encoded))
        return {
            "frame_offset": frame_offset,
            "stream_offset": stream_base + index,
            "original": original[index:index + 8].hex(),
            "encoded": encoded[index:index + 8].hex(),
        }
    return None


def _check_frame(stream, offset, counter, body, trailer_size):
    assert stream[offset:offset + len(MARKER)] == MARKER
    flags4 = stream[offset + 8:offset + 12]
    assert len(flags4) == 4
    trailer_offset = offset + FRAME_HEADER_SIZE + len(body)
    trailer_value, size = read_frame_prefix_varint(stream, trailer_offset)
    assert trailer_value is not None and size == trailer_size
    encoded = encode_frame(counter, flags4, body, trailer_value)
    original = stream[offset:trailer_offset + trailer_size]
    assert len(original) == FRAME_HEADER_SIZE + len(body) + trailer_size
    return original, encoded


def _check_record_readers(body, start, v1, v2, large):
    v1_mask, v1_mask_size = read_mask_varint(body, start)
    v1_prefix, v1_prefix_size = read_record_prefix_varint(body, start)
    assert v1_mask == v1 and v1_mask_size > 0
    assert v1_prefix is not None and v1_prefix_size > 0
    if v1 < 0x80:
        assert (v1_prefix, v1_prefix_size) == (v1, v1_mask_size)
    v2_start = start + v1_mask_size + 1
    v2_mask, v2_mask_size = read_mask_varint(body, v2_start)
    v2_prefix, v2_prefix_size = read_record_prefix_varint(body, v2_start)
    assert v2_mask == v2 and v2_mask_size > 0
    assert v2_prefix is not None and v2_prefix_size > 0
    if v2 < 0x80:
        assert (v2_prefix, v2_prefix_size) == (v2, v2_mask_size)
    if v1 >= 0x80:
        large["v1"] += 1
        if (v1_mask, v1_mask_size) != (v1_prefix, v1_prefix_size):
            large["disagreements"] += 1
    if v2 >= 0x80:
        large["v2"] += 1
        if (v2_mask, v2_mask_size) != (v2_prefix, v2_prefix_size):
            large["disagreements"] += 1


def _check_records(body):
    rebuilt = bytearray()
    records_seen = 0
    last_end = 0
    large = {"v1": 0, "v2": 0, "disagreements": 0}
    for start, v1, v2, _group_mask, payload_offset, _fields in iter_records(body):
        records_seen += 1
        _check_record_readers(body, start, v1, v2, large)
        fields, payload_size = decode_record_payload(body, payload_offset)
        assert fields is not None and payload_size > 0
        payload_end = payload_offset + payload_size
        assert payload_end <= len(body)
        rebuilt.extend(encode_record(v1, v2, 11, body[payload_offset:payload_end]))
        last_end = payload_end
    if records_seen == 0:
        return {
            "status": "no_records",
            "records_seen": 0,
            "rebuilt": b"",
            "large": large,
        }
    if last_end != len(body):
        return {
            "status": "incomplete",
            "records_seen": records_seen,
            "rebuilt": bytes(rebuilt),
            "large": large,
        }
    return {
        "status": "complete",
        "records_seen": records_seen,
        "rebuilt": bytes(rebuilt),
        "large": large,
    }


def _new_report(path, stream):
    return {
        "ledger": str(path),
        "stream_bytes": len(stream),
        "frames_tested": 0,
        "frames_identical": 0,
        "frames_different": 0,
        "first_frame_difference": None,
        "counter_deltas": collections.Counter(),
        "record_bodies_complete": 0,
        "record_bodies_incomplete": 0,
        "record_bodies_without_records": 0,
        "records_seen": 0,
        "records_rebuilt": 0,
        "record_bodies_identical": 0,
        "record_bodies_different": 0,
        "first_record_difference": None,
        "record_counts": collections.Counter(),
        "large_v1": 0,
        "large_v2": 0,
        "reader_disagreements": 0,
    }


def analyze_ledger(path):
    stream = channel_stream(str(path))
    report = _new_report(path, stream)
    previous_counter = None
    for offset, counter, body, trailer_size in iter_frames(stream):
        report["frames_tested"] += 1
        if previous_counter is not None:
            report["counter_deltas"][(counter - previous_counter) & MAX_U32] += 1
        previous_counter = counter

        original, encoded = _check_frame(stream, offset, counter, body, trailer_size)
        if original == encoded:
            report["frames_identical"] += 1
        else:
            report["frames_different"] += 1
            if report["first_frame_difference"] is None:
                report["first_frame_difference"] = _difference(offset, original, encoded)

        record = _check_records(body)
        status = record["status"]
        if status == "complete":
            report["record_bodies_complete"] += 1
            report["records_rebuilt"] += record["records_seen"]
            report["record_counts"][record["records_seen"]] += 1
            if record["rebuilt"] == body:
                report["record_bodies_identical"] += 1
            else:
                report["record_bodies_different"] += 1
                if report["first_record_difference"] is None:
                    report["first_record_difference"] = _difference(
                        offset, body, record["rebuilt"], offset + FRAME_HEADER_SIZE
                    )
        elif status == "incomplete":
            report["record_bodies_incomplete"] += 1
        else:
            assert status == "no_records"
            report["record_bodies_without_records"] += 1
        report["records_seen"] += record["records_seen"]
        report["large_v1"] += record["large"]["v1"]
        report["large_v2"] += record["large"]["v2"]
        report["reader_disagreements"] += record["large"]["disagreements"]
    return report


def _counter_distribution(counter):
    return ", ".join(f"{delta}:{count}" for delta, count in sorted(counter.items()))


def print_report(report):
    print(f"ledger: {report['ledger']}")
    print(f"  channel-1 stream: {report['stream_bytes']} bytes")
    print(f"  frames tested: {report['frames_tested']}")
    print(f"  frames identical: {report['frames_identical']}")
    print(f"  frames different: {report['frames_different']}")
    if report["first_frame_difference"] is not None:
        print(f"  first frame difference: {report['first_frame_difference']}")
    print(f"  counter delta distribution: {{{_counter_distribution(report['counter_deltas'])}}}")
    print(f"  ALC-only bodies consumed completely: {report['record_bodies_complete']}")
    print(f"  ALC-only records rebuilt: {report['records_rebuilt']}")
    print(f"  complete-body records per body: {sorted(report['record_counts'].items())}")
    print(f"  bodies with partial record walks: {report['record_bodies_incomplete']}")
    print(f"  bodies without ALC records: {report['record_bodies_without_records']}")
    print(f"  records yielded by iter_records: {report['records_seen']}")
    print(f"  complete record bodies identical: {report['record_bodies_identical']}")
    print(f"  complete record bodies different: {report['record_bodies_different']}")
    if report["first_record_difference"] is not None:
        print(f"  first record difference: {report['first_record_difference']}")
    large = report["large_v1"] + report["large_v2"]
    print(f"  V1/V2 values >= 0x80: {large} (V1={report['large_v1']}, V2={report['large_v2']})")
    print(f"  V1/V2 mask-prefix reader disagreements: {report['reader_disagreements']}")


def check():
    for path in CAPTURES:
        report = analyze_ledger(path)
        print_report(report)
        assert report["frames_tested"] > 0
        assert report["frames_tested"] == report["frames_identical"]
        assert report["frames_different"] == 0
        assert report["record_bodies_complete"] == report["record_bodies_identical"]
        assert report["record_bodies_different"] == 0
        assert report["reader_disagreements"] == 0
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv != ["--check"]:
        raise SystemExit("usage: encode_record.py --check")
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
