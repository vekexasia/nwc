#!/usr/bin/env python3
"""Offline diagnostic for a saved New World DTLS ledger.

This is deliberately a rejection-first experiment. It reuses the existing
Carrier decoder, validates chunk countdown reassembly per SSL connection, and
only accepts a position after a complete application schema has consumed its
bytes. It does not scan floats or emit raw payloads.
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

from decode_dtls_ledger import (  # noqa: E402
    LEDGER_MAGIC,
    decode_record,
    parse_carrier_messages,
    iter_ledger,
)


STANDARD_MARKER = b"\x00\x01\x08\x01"
STANDARD_CONSTANT = b"\x01\x01\x01\x01\x00\x00"
MAX_VARINT_BYTES = 5
MAX_INDEX_COUNT = 4096
MAX_PAYLOAD_LENGTH = 8 * 1024 * 1024


def _sequence_break(previous, current):
    return (previous is not None and current is not None
            and current != ((previous + 1) & 0xFFFF))


def reassemble_channel_messages(rows):
    """Join Carrier chunks using the observed countdown convention.

    A chunked run starts at N, continues N-1 .. 2, and is completed by the
    following non-chunked Carrier message. Unknown or broken boundaries are
    rejected instead of being concatenated. Callers must provide rows from one
    SSL connection and one direction/channel only.
    """
    complete = []
    pending = None
    errors = collections.Counter()

    def add_single(record_index, ts_ms, message):
        complete.append({
            "record_index": record_index,
            "ts_ms": ts_ms,
            "seq": message.seq,
            "rel_seq": message.rel_seq,
            "parts": 1,
            "payload": message.payload,
        })

    for record_index, ts_ms, message in rows:
        if message.num_chunks is not None:
            if message.num_chunks < 2:
                errors["invalid_chunk_count"] += 1
                continue
            if pending is None:
                pending = {
                    "total": message.num_chunks,
                    "next": message.num_chunks - 1,
                    "parts": [message.payload],
                    "last_seq": message.seq,
                    "start": (record_index, ts_ms, message.seq,
                              message.rel_seq),
                }
                continue
            if message.num_chunks != pending["next"]:
                errors["chunk_countdown_break"] += 1
                pending = None
                continue
            if _sequence_break(pending["last_seq"], message.seq):
                errors["chunk_sequence_break"] += 1
                pending = None
                continue
            pending["parts"].append(message.payload)
            pending["last_seq"] = message.seq
            pending["next"] -= 1
            continue

        if pending is None:
            add_single(record_index, ts_ms, message)
            continue
        if pending["next"] != 1:
            errors["chunk_countdown_incomplete"] += 1
            pending = None
            add_single(record_index, ts_ms, message)
            continue
        if _sequence_break(pending["last_seq"], message.seq):
            errors["chunk_sequence_break"] += 1
            pending = None
            add_single(record_index, ts_ms, message)
            continue
        complete.append({
            "record_index": pending["start"][0],
            "ts_ms": pending["start"][1],
            "seq": pending["start"][2],
            "rel_seq": pending["start"][3],
            "parts": pending["total"],
            "payload": b"".join(pending["parts"]) + message.payload,
        })
        pending = None

    if pending is not None:
        errors["unterminated_chunk_group"] += 1

    return complete, errors


def find_all(data, needle):
    start = 0
    while True:
        offset = data.find(needle, start)
        if offset < 0:
            return
        yield offset
        start = offset + 1


def _read_bounded_varint(data, offset, limit, maximum):
    value = 0
    for index in range(MAX_VARINT_BYTES):
        if offset >= limit:
            return None, offset, "truncated"
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << (7 * index)
        if not byte & 0x80:
            if value > maximum:
                return None, offset, "out_of_range"
            return value, offset, None
    return None, offset, "overlong"


def parse_state_bundle_hypothesis(data, start):
    """Parse the documented StateBundle hypothesis without skipping bytes."""
    offset = start
    limit = len(data)
    if offset >= limit:
        return "has_sequence_missing", offset

    has_sequence = data[offset]
    offset += 1
    if has_sequence not in (0, 1):
        return "has_sequence_invalid", offset
    if has_sequence:
        _, offset, error = _read_bounded_varint(
            data, offset, limit, 0xFFFFFFFF)
        if error:
            return f"sequence_{error}", offset

    for field_name in ("chunk_class_missing", "chunk_kind_missing"):
        if offset >= limit:
            return field_name, offset
        offset += 1

    for field_name in ("bool_a", "bool_b"):
        if offset >= limit:
            return f"{field_name}_missing", offset
        value = data[offset]
        offset += 1
        if value not in (0, 1):
            return f"{field_name}_invalid", offset

    if data[offset - 1]:
        _, offset, error = _read_bounded_varint(
            data, offset, limit, 0xFFFFFFFF)
        if error:
            return f"hint_{error}", offset
        count, offset, error = _read_bounded_varint(
            data, offset, limit, MAX_INDEX_COUNT)
        if error:
            return f"count_{error}", offset
        if count * 2 > limit - offset:
            return "index_list_truncated", offset
        offset += count * 2

    payload_length, offset, error = _read_bounded_varint(
        data, offset, limit, MAX_PAYLOAD_LENGTH)
    if error:
        return f"payload_len_{error}", offset
    if payload_length > limit - offset:
        return "payload_truncated", offset
    offset += payload_length
    if offset != limit:
        return "payload_leftover", offset
    return "accepted", offset


def parse_inbound_application_stream(pieces):
    """Cut complete IN messages from the reassembled channel byte stream."""
    stream = b"".join(item["payload"] for item in pieces)
    messages = []
    framing = collections.Counter()
    offset = 0
    while offset < len(stream):
        length, body_start, error = _read_bounded_varint(
            stream, offset, len(stream), MAX_PAYLOAD_LENGTH)
        if error:
            framing[f"inbound_length_{error}"] += 1
            break
        if length > len(stream) - body_start:
            framing["inbound_message_truncated"] += 1
            break
        messages.append({"payload": stream[body_start:body_start + length]})
        offset = body_start + length
    return messages, framing, len(stream) - offset





def analyze_application(messages):
    """Test only bounded, source-backed envelope hypotheses."""
    stats = collections.Counter()
    marker_positions = collections.Counter()
    marker_body_first = collections.Counter()
    hypothesis_rejections = collections.Counter()
    standard_type8_at_start = 0
    standard_type8_anchor_like_occurrences = 0
    standard_type8_anchor_like_at_offset_3 = 0
    candidate_marker_messages = 0
    candidate_marker_occurrences = 0
    exact_candidates = 0
    hypothesis_leftover_bytes = collections.Counter()

    for message in messages:
        payload = message["payload"]
        if payload.startswith(STANDARD_MARKER):
            standard_type8_at_start += 1
        offsets = list(find_all(payload, STANDARD_MARKER))
        if not offsets:
            continue
        candidate_marker_messages += 1
        candidate_marker_occurrences += len(offsets)
        for offset in offsets:
            marker_positions[offset] += 1
            if (offset + len(STANDARD_MARKER) + 1
                    + len(STANDARD_CONSTANT) <= len(payload)
                    and payload[offset + len(STANDARD_MARKER) + 1:
                                offset + len(STANDARD_MARKER) + 1
                                + len(STANDARD_CONSTANT)] == STANDARD_CONSTANT):
                standard_type8_anchor_like_occurrences += 1
                if offset == 3:
                    standard_type8_anchor_like_at_offset_3 += 1
            body_offset = offset + len(STANDARD_MARKER)
            if body_offset >= len(payload):
                marker_body_first["missing"] += 1
                hypothesis_rejections["has_sequence_missing"] += 1
                continue
            first = payload[body_offset]
            marker_body_first["valid_has_sequence"] += first in (0, 1)
            marker_body_first["invalid_has_sequence"] += first not in (0, 1)
            outcome, consumed = parse_state_bundle_hypothesis(
                payload, body_offset)
            hypothesis_rejections[outcome] += 1
            if outcome == "payload_leftover":
                hypothesis_leftover_bytes[len(payload) - consumed] += 1
            if outcome == "accepted":
                exact_candidates += 1

    stats.update({
        "application_messages": len(messages),
        "application_boundary_status": (
            "in_varint_length_framed_stream; carrier pieces joined"),
        "standard_type8_marker_at_message_start": standard_type8_at_start,
        "standard_type8_anchor_like_occurrences": standard_type8_anchor_like_occurrences,
        "standard_type8_anchor_like_at_offset_3": standard_type8_anchor_like_at_offset_3,
        "marker_like_messages": candidate_marker_messages,
        "marker_like_occurrences": candidate_marker_occurrences,
        "state_bundle_hypothesis_candidates": candidate_marker_occurrences,
        "state_bundle_hypothesis_first_field_valid": (
            marker_body_first["valid_has_sequence"]),
        "state_bundle_hypothesis_exact_consumption": exact_candidates,
        "state_bundle_hypothesis_leftover_bytes": dict(
            sorted(hypothesis_leftover_bytes.items())),
    })
    return stats, marker_positions, marker_body_first, hypothesis_rejections
def sequence_summary(rows):
    values = [message.seq for _, _, message in rows if message.seq is not None]
    reliable = [
        message.rel_seq for _, _, message in rows
        if message.rel_seq is not None and message.flags & 0x01
    ]

    def summarize(items):
        if not items:
            return {}
        counts = collections.Counter(items)
        unique = sorted(counts)
        order_breaks = sum(_sequence_break(before, after)
                           for before, after in zip(items, items[1:]))
        gaps = sum(1 for before, after in zip(unique, unique[1:])
                   if ((after - before) & 0xFFFF) > 1)
        return {
            "first": items[0],
            "last": items[-1],
            "count": len(items),
            "unique": len(unique),
            "duplicate_items": sum(n - 1 for n in counts.values() if n > 1),
            "gaps": gaps,
            "order_breaks": order_breaks,
        }

    return summarize(values), summarize(reliable)


def _ledger_coverage(ledger_path):
    size = ledger_path.stat().st_size
    offset = 0
    records = 0
    with ledger_path.open("rb") as handle:
        data = handle.read()
    while offset + 28 <= size:
        magic, _, _, _, _, _, _, payload_length = struct.unpack_from(
            "<IQBBBBQI", data, offset)
        if magic != LEDGER_MAGIC or offset + 28 + payload_length > size:
            break
        offset += 28 + payload_length
        records += 1
    return {
        "file_bytes": size,
        "record_bytes": offset,
        "records": records,
        "trailing_bytes": size - offset,
        "complete": offset == size,
    }


def _connection_summary(label, item):
    rows = item["rows"]
    reassembled, reassembly_errors = reassemble_channel_messages(rows)
    application_messages, application_framing, application_trailing = (
        parse_inbound_application_stream(reassembled))
    application, marker_positions, marker_body_first, hypothesis_rejections = (
        analyze_application(application_messages))
    chunk_parts = collections.Counter(
        message["parts"] for message in reassembled if message["parts"] > 1)
    sequence, reliable_sequence = sequence_summary(rows)
    timestamps = item["timestamps"]
    return {
        "label": label,
        "datagrams": item["datagrams"],
        "directions": dict(item["directions"]),
        "timestamp_ms": {"first": min(timestamps), "last": max(timestamps)},
        "carrier_trailers": {
            "datagrams": item["trailer_datagrams"],
            "bytes": item["trailer_bytes"],
        },
        "in_ch1_carrier_messages": len(rows),
        "in_ch1_carrier_sequence": sequence,
        "in_ch1_reliable_sequence": reliable_sequence,
        "reassembled": len(reassembled),
        "application_stream": {
            "complete_messages": len(application_messages),
            "framing_errors": dict(application_framing),
            "trailing_bytes": application_trailing,
        },
        "reassembled_chunk_parts": dict(sorted(chunk_parts.items())),
        "reassembly_errors": dict(reassembly_errors),
        "application": dict(application),
        "marker_like_positions": dict(sorted(marker_positions.items())),
        "marker_like_body_first": dict(marker_body_first),
        "state_bundle_hypothesis_rejections": dict(hypothesis_rejections),
    }


def _invalid_result(ledger_path, coverage):
    application, marker_positions, marker_body_first, hypothesis_rejections = (
        analyze_application([]))
    return {
        "status": "invalid_ledger_incomplete",
        "ledger": str(ledger_path),
        "ledger_coverage": coverage,
        "datagrams": 0,
        "decoder_accepted_datagrams": 0,
        "carrier_fully_consumed_datagrams": 0,
        "decoder_errors": {},
        "carrier_errors": {},
        "directions": {},
        "carrier_messages": 0,
        "channels": {},
        "trailers": {},
        "connections": [],
        "in_ch1_carrier_messages": 0,
        "reassembled": 0,
        "reassembled_chunk_parts": {},
        "reassembly_errors": {},
        "application_stream": {
            "complete_messages": 0,
            "framing_errors": {},
            "trailing_bytes": 0,
        },
        "application": dict(application),
        "marker_like_positions": dict(marker_positions),
        "marker_like_body_first": dict(marker_body_first),
        "state_bundle_hypothesis_rejections": dict(hypothesis_rejections),
        "candidate_type13_members": None,
        "candidate_type13_status": "not_attempted_invalid_ledger",
        "coordinate_points": None,
        "coordinate_status": "not_attempted_invalid_ledger",
        "coordinates": [],
        "position_result": "not attempted: incomplete ledger coverage",
    }
def run(ledger_path):
    ledger_path = Path(ledger_path)
    coverage = _ledger_coverage(ledger_path)
    if not coverage["complete"]:
        return _invalid_result(ledger_path, coverage)
    datagrams = 0
    decoder_accepted_datagrams = 0
    fully_consumed_datagrams = 0
    decoder_errors = collections.Counter()
    carrier_errors = collections.Counter()
    trailers = collections.Counter()
    by_dir = collections.Counter()
    by_channel = collections.Counter()
    carrier_messages = 0
    by_connection = collections.OrderedDict()
    connection_generations = collections.Counter()
    last_ssl_ptr = None
    active_connection_key = None
    for index, dir_byte, ts_ms, ssl_ptr, payload in iter_ledger(ledger_path):
        datagram = decode_record(index, dir_byte, ts_ms, ssl_ptr, payload)
        if ssl_ptr != last_ssl_ptr:
            connection_generations[ssl_ptr] += 1
            active_connection_key = (ssl_ptr, connection_generations[ssl_ptr])
            last_ssl_ptr = ssl_ptr
        connection = by_connection.setdefault(active_connection_key, {
            "datagrams": 0,
            "directions": collections.Counter(),
            "timestamps": [],
            "trailer_datagrams": 0,
            "trailer_bytes": 0,
            "rows": [],
        })
        datagrams += 1
        connection["datagrams"] += 1
        connection["directions"][datagram.dir] += 1
        connection["timestamps"].append(ts_ms)
        by_dir[datagram.dir] += 1
        if datagram.error:
            decoder_errors[datagram.error] += 1
        else:
            decoder_accepted_datagrams += 1
        if datagram.carrier_error:
            carrier_errors[datagram.carrier_error] += 1
        if not datagram.trailer:
            fully_consumed_datagrams += 1
        if datagram.trailer:
            trailers["datagrams"] += 1
            trailers["bytes"] += len(datagram.trailer)
            connection["trailer_datagrams"] += 1
            connection["trailer_bytes"] += len(datagram.trailer)
        for message in datagram.messages:
            carrier_messages += 1
            channel = message.channel
            channel_name = (f"ch{channel}" if channel is not None
                            else "no_channel")
            by_channel[(datagram.dir, channel_name)] += 1
            if datagram.dir == "in" and channel == 1:
                connection["rows"].append((index, ts_ms, message))

    connections = []
    all_application_messages = []
    all_application_framing = collections.Counter()
    all_application_trailing = 0
    all_reassembly_errors = collections.Counter()
    all_chunk_parts = collections.Counter()
    for number, connection in enumerate(by_connection.values(), 1):
        summary = _connection_summary(f"conn-{number:02d}", connection)
        connections.append(summary)
        all_reassembly_errors.update(summary["reassembly_errors"])
        all_chunk_parts.update(summary["reassembled_chunk_parts"])
        all_application_framing.update(
            summary["application_stream"]["framing_errors"])
        all_application_trailing += summary["application_stream"]["trailing_bytes"]
        # The payloads are consumed only by the bounded in-memory diagnostic.
        rows = connection["rows"]
        reassembled, _ = reassemble_channel_messages(rows)
        application_messages, _, _ = parse_inbound_application_stream(reassembled)
        all_application_messages.extend(application_messages)
    application, marker_positions, marker_body_first, hypothesis_rejections = (
        analyze_application(all_application_messages))
    state_bundle_exact = application["state_bundle_hypothesis_exact_consumption"]
    position_result = (
        "none: no exact StateBundle candidate; inner member boundaries not attempted"
        if not state_bundle_exact else
        "not decoded: member body decoder is not implemented")

    return {
        "ledger": str(ledger_path),
        "status": "ok",
        "ledger_coverage": coverage,
        "datagrams": datagrams,
        "decoder_accepted_datagrams": decoder_accepted_datagrams,
        "carrier_errors": dict(carrier_errors),
        "carrier_fully_consumed_datagrams": fully_consumed_datagrams,
        "decoder_errors": dict(decoder_errors),
        "directions": dict(by_dir),
        "carrier_messages": carrier_messages,
        "channels": {f"{direction}:{channel}": count
                     for (direction, channel), count in sorted(by_channel.items())},
        "trailers": dict(trailers),
        "connections": connections,
        "in_ch1_carrier_messages": sum(
            item["in_ch1_carrier_messages"] for item in connections),
        "reassembled": sum(item["reassembled"] for item in connections),
        "application_stream": {
            "complete_messages": len(all_application_messages),
            "framing_errors": dict(all_application_framing),
            "trailing_bytes": all_application_trailing,
        },
        "reassembled_chunk_parts": dict(sorted(all_chunk_parts.items())),
        "reassembly_errors": dict(all_reassembly_errors),
        "application": dict(application),
        "marker_like_positions": dict(sorted(marker_positions.items())),
        "marker_like_body_first": dict(marker_body_first),
        "state_bundle_hypothesis_rejections": dict(hypothesis_rejections),
        "candidate_type13_members": None,
        "candidate_type13_status": "not_attempted_no_exact_bundle",
        "coordinate_points": None,
        "coordinate_status": "not_attempted_no_exact_bundle",
        "coordinates": [],
        "position_result": position_result,
    }


def print_report(result):
    print("Offline saved-position diagnostic")
    print(f"  status: {result.get('status', 'ok')}")
    print(f"  ledger coverage: {result['ledger_coverage']}")
    print(f"  datagrams: {result['decoder_accepted_datagrams']}/{result['datagrams']} decoder-accepted")
    print(f"  Carrier fully consumed: {result['carrier_fully_consumed_datagrams']}/{result['datagrams']}")
    print(f"  decoder errors: {sum(result['decoder_errors'].values())}")
    print(f"  Carrier parse rejections: {result['carrier_errors'] or 'none'}")
    print(f"  carrier messages: {result['carrier_messages']}")
    print(f"  IN ch1 messages: {result['in_ch1_carrier_messages']}")
    print(f"  ch1 reassembled messages: {result['reassembled']}")
    print(f"  reassembled chunk groups by part count: {result['reassembled_chunk_parts']}")
    print(f"  reassembly errors: {result['reassembly_errors'] or 'none'}")
    print(f"  IN application messages: {result['application_stream']['complete_messages']}")
    print(f"  IN application framing: {result['application_stream']['framing_errors'] or 'none'}; trailing bytes: {result['application_stream']['trailing_bytes']}")
    print(f"  Carrier trailers: {result['trailers'] or 'none'}")
    for connection in result["connections"]:
        print(f"  {connection['label']}: {connection['timestamp_ms']} "
              f"ch1={connection['in_ch1_carrier_messages']} "
              f"reassembled={connection['reassembled']} "
              f"seq={connection['in_ch1_carrier_sequence']}")
    print(f"  First Light type-8 marker at message start: "
          f"{result['application']['standard_type8_marker_at_message_start']}")
    print(f"  type-8 anchor-like patterns (not proven headers): "
          f"{result['application']['standard_type8_anchor_like_occurrences']} "
          f"({result['application']['standard_type8_anchor_like_at_offset_3']} at offset 3)")
    print(f"  marker-like 00 01 08 01: "
          f"{result['application']['marker_like_occurrences']} occurrences in "
          f"{result['application']['marker_like_messages']} messages")
    print(f"  marker-like offsets: {result['marker_like_positions']}")
    print(f"  first hypothesis field: {result['marker_like_body_first']}")
    print(f"  StateBundle hypothesis rejection: "
          f"{result['state_bundle_hypothesis_rejections']}")
    print(f"  StateBundle leftover bytes at rejection: "
          f"{result['application']['state_bundle_hypothesis_leftover_bytes']}")
    print(f"  type-13 members: {result['candidate_type13_members']} "
          f"({result['candidate_type13_status']})")
    print(f"  coordinate points: {result['coordinate_points']} "
          f"({result['coordinate_status']})")
    print(f"  positions: {result['position_result']}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("ledger", type=Path)
    parser.add_argument("--out-json", type=Path,
                        help="write bounded aggregate diagnostics, never payload bytes")
    args = parser.parse_args()
    result = run(args.ledger)
    print_report(result)
    if args.out_json:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        with args.out_json.open("w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2, sort_keys=True)
            handle.write("\n")
        args.out_json.chmod(0o600)
    return 0 if result.get("status", "ok") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
