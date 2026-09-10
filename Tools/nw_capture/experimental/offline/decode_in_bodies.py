#!/usr/bin/env python3
"""Decode inbound New World channel-1 bodies into records.

Two verified layers, one hypothesis:

  1. Frame (verified structurally against real captures): on the reassembled IN channel-1
     stream a message is

         00 01 08 01        4 bytes, constant
         u32 LE             counter, +1 per message on the stream (96.4% of gaps)
         u32                constant 0x00010104 in the Test-teleport session
         u16 BE             body length
         body
         varint             prefix-coded trailing integer (see below)

     The trailer uses the prefix-coded variable u32 that the binary itself implements
     (writer FUN_140877970, reader FUN_14087b5c0): 1 byte `0xxxxxxx` (7 payload bits),
     2 bytes `10xxxxxx` (6), 3 `110xxxxx` (5), 4 `1110xxxx` (4), 5 `11110xxx` (3). It is
     NOT the 7-bit continuation (LEB128) form.

  2. Records (hypothesis, measured): a body is a leading byte followed by N records of

        01 10 0b 01        4-byte record tag observed in every sampled body
        varint             prefix-coded value (a replica/entity-sized number)
        payload            4 to 6 bytes in the sampled families

     This module reports how far that hypothesis goes; it never pretends to consume bytes
     it cannot explain.

Usage:
    .venv-capture/bin/python Tools/nw_capture/experimental/offline/decode_in_bodies.py \
        Tools/nw_capture/captures/<session>/dtls/ledger.bin --json out.json
"""
from __future__ import annotations

import argparse
import collections
import json
import struct
import sys
from pathlib import Path

_CAPTURE_TOOL = Path(__file__).resolve().parents[2]
if str(_CAPTURE_TOOL) not in sys.path:
    sys.path.insert(0, str(_CAPTURE_TOOL))

from decode_dtls_ledger import decode_record, iter_ledger  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from decode_saved_position import reassemble_channel_messages  # noqa: E402

MARKER = b"\x00\x01\x08\x01"
RECORD_TAG = bytes.fromhex("01100b01")
FRAME_HEADER = 14           # marker + counter + 4 constant bytes
MAX_PREFIX_BYTES = 5


def read_prefix_varint(data, offset):
    """Prefix-coded variable u32 as implemented by FUN_14087b5c0. Returns (value, size)."""
    if offset >= len(data):
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
        return (((data[offset + 1] << 8 | data[offset + 2]) << 5) | (first & 0x1F)), 3
    if first < 0xF0:
        if offset + 3 >= len(data):
            return None, 0
        value = data[offset + 1] << 16 | data[offset + 2] << 8 | data[offset + 3]
        return ((value << 4) | (first & 0x0F)), 4
    if offset + 4 >= len(data):
        return None, 0
    value = (data[offset + 1] << 24 | data[offset + 2] << 16
             | data[offset + 3] << 8 | data[offset + 4])
    return ((value << 3) | (first & 0x07)), 5


def find_all(data, needle):
    start = 0
    while True:
        index = data.find(needle, start)
        if index < 0:
            return
        yield index
        start = index + 1


def channel_stream(ledger_path, direction="in", channel=1):
    """Reassemble one direction/channel of a ledger into one byte stream."""
    rows = []
    for index, dir_byte, ts_ms, ssl_ptr, payload in iter_ledger(Path(ledger_path)):
        datagram = decode_record(index, dir_byte, ts_ms, ssl_ptr, payload)
        if datagram.dir != direction:
            continue
        for message in datagram.messages:
            if message.channel == channel:
                rows.append((index, ts_ms, message))
    if not rows:
        return b""
    # Reassembly is per SSL connection in the full decoder; a single connection carrying
    # channel-1 traffic is the common case and is what the frame statistics were measured on.
    pieces, _ = reassemble_channel_messages(rows)
    return b"".join(piece["payload"] for piece in pieces)


def iter_frames(stream):
    """Yield (offset, counter, body, trailer_size) for every frame that closes exactly."""
    positions = list(find_all(stream, MARKER))
    for offset, following in zip(positions, positions[1:]):
        length = struct.unpack_from(">H", stream, offset + 12)[0]
        body_start = offset + FRAME_HEADER
        body = stream[body_start:body_start + length]
        trailer = following - (body_start + length)
        if 1 <= trailer <= MAX_PREFIX_BYTES:
            value, size = read_prefix_varint(stream, body_start + length)
            if value is not None and size == trailer:
                counter = struct.unpack_from("<I", stream, offset + 4)[0]
                yield offset, counter, body, trailer


def split_records(body):
    """Split a body into (leading, records, leftover) using the record tag hypothesis.

    Returns (leading_bytes, [(tag, varint_value, payload)], leftover_bytes).
    """
    positions = list(find_all(body, RECORD_TAG))
    if not positions:
        return body, [], b""
    leading = body[:positions[0]]
    records = []
    for index, start in enumerate(positions):
        end = positions[index + 1] if index + 1 < len(positions) else len(body)
        segment = body[start + len(RECORD_TAG):end]
        value, size = read_prefix_varint(segment, 0)
        if value is None or size == 0:
            records.append((RECORD_TAG, None, segment))
            continue
        records.append((RECORD_TAG, value, segment[size:]))
    # the last record's payload may in fact run to the end of the body: leftover is only
    # meaningful when the trailing bytes cannot be split, so we report the tail as payload
    return leading, records, b""


def analyze(ledger_path, limit=None):
    stream = channel_stream(ledger_path)
    result = {
        "ledger": str(ledger_path),
        "in_ch1_bytes": len(stream),
        "frames": 0,
        "frames_exact": 0,
        "bodies_with_records": 0,
        "records_total": 0,
        "record_tag_prefixes": collections.Counter(),
        "leading_byte": collections.Counter(),
        "payload_sizes": collections.Counter(),
        "varint_values_sample": [],
        "counter_gaps_plus_one": 0,
        "counter_gaps_other": 0,
        "frames_fully_split": 0,
        "unexplained_frames": [],
    }
    previous_counter = None
    for offset, counter, body, trailer in iter_frames(stream):
        result["frames"] += 1
        if previous_counter is not None:
            if counter - previous_counter == 1:
                result["counter_gaps_plus_one"] += 1
            else:
                result["counter_gaps_other"] += 1
        previous_counter = counter
        leading, records, leftover = split_records(body)
        if records:
            result["bodies_with_records"] += 1
            result["records_total"] += len(records)
            result["leading_byte"][leading.hex()] += 1
            for _, value, payload in records:
                result["payload_sizes"][len(payload)] += 1
                if value is not None and len(result["varint_values_sample"]) < 200:
                    result["varint_values_sample"].append(value)
            if len(leading) + sum(4 + _varint_size(v) + len(p) for _, v, p in records) == len(body):
                result["frames_fully_split"] += 1
        else:
            if len(result["unexplained_frames"]) < 5:
                result["unexplained_frames"].append(body[:24].hex())
        if limit is not None and result["frames"] >= limit:
            break
    return result


def _varint_size(value):
    if value is None:
        return 5
    if value < 0x80:
        return 1
    if value < 0x4000:
        return 2
    if value < 0x200000:
        return 3
    if value < 0x10000000:
        return 4
    return 5


def print_report(result):
    print(f"ledger: {result['ledger']}")
    print(f"  IN channel-1 stream: {result['in_ch1_bytes']} bytes")
    print(f"  frames closing with the prefix-coded trailer: {result['frames']}")
    print(f"  counter continuity: +1 in {result['counter_gaps_plus_one']}, "
          f"other in {result['counter_gaps_other']}")
    print(f"  bodies containing the record tag: {result['bodies_with_records']}")
    print(f"  records parsed: {result['records_total']}")
    print(f"  bodies split exactly (leading + records == body): {result['frames_fully_split']}")
    print(f"  leading bytes before the first tag: {result['leading_byte'].most_common(5)}")
    print(f"  per-record payload sizes: {result['payload_sizes'].most_common(8)}")
    values = result["varint_values_sample"]
    if values:
        print(f"  record varint values: n={len(values)} min={min(values)} max={max(values)} "
              f"first={values[:8]}")
    if result["unexplained_frames"]:
        print(f"  bodies without the tag (first bytes): {result['unexplained_frames']}")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("ledger", type=Path)
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)
    result = analyze(args.ledger, args.limit)
    print_report(result)
    if args.json:
        serializable = {k: (dict(v) if isinstance(v, collections.Counter) else v)
                        for k, v in result.items()}
        args.json.write_text(json.dumps(serializable, indent=1))
        print(f"json: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
