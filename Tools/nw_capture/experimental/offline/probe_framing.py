#!/usr/bin/env python3
"""S1 probe: does the reported Message V3 signature 0x970C0A5D frame the channel-1 stream?

Read-only. Reuses the existing Carrier decoder to rebuild the IN channel-1 byte stream,
then looks for the reported signature and for the marker the offline decoder currently
guesses (00 01 08 01). It tests whether constant-size length fields right after the
signature explain the gap to the next occurrence, which is what a real framing would do.

Success criterion for S1 (plan): at least one application message that consumes every byte
it claims. Here that means an (offset, encoding) combination whose declared length accounts
for essentially every consecutive gap, not a handful of coincidences.
"""
from __future__ import annotations

import argparse
import collections
import struct
import sys
from pathlib import Path

_CAPTURE_TOOL = Path(__file__).resolve().parents[2]
if str(_CAPTURE_TOOL) not in sys.path:
    sys.path.insert(0, str(_CAPTURE_TOOL))

from decode_dtls_ledger import decode_record, iter_ledger  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from decode_saved_position import reassemble_channel_messages  # noqa: E402

SIGNATURE = 0x970C0A5D
CANDIDATES = {
    "sig-LE 5D0A0C97": struct.pack("<I", SIGNATURE),
    "sig-BE 970C0A5D": struct.pack(">I", SIGNATURE),
    "old 00010801": b"\x00\x01\x08\x01",
}


def find_all(data, needle):
    start = 0
    while True:
        offset = data.find(needle, start)
        if offset < 0:
            return
        yield offset
        start = offset + 1


def read_varint(data, offset, limit):
    value = 0
    for index in range(5):
        if offset >= limit:
            return None
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << (7 * index)
        if not byte & 0x80:
            return value
    return None


def declared_values(data, offset):
    """Candidate length fields right after a marker occurrence."""
    out = {}
    for shift in range(4, 13):
        pos = offset + shift
        if pos + 4 > len(data):
            continue
        out[(shift, "u16le")] = struct.unpack_from("<H", data, pos)[0]
        out[(shift, "u16be")] = struct.unpack_from(">H", data, pos)[0]
        out[(shift, "u32le")] = struct.unpack_from("<I", data, pos)[0]
        out[(shift, "u32be")] = struct.unpack_from(">I", data, pos)[0]
        out[(shift, "varint")] = read_varint(data, pos, len(data))
    return out


def channel_streams(ledger_path):
    """Yield (label, reassembled channel-1 byte stream) per SSL connection."""
    last_ssl = None
    generation = collections.Counter()
    key = None
    by_connection = collections.OrderedDict()
    for index, dir_byte, ts_ms, ssl_ptr, payload in iter_ledger(ledger_path):
        datagram = decode_record(index, dir_byte, ts_ms, ssl_ptr, payload)
        if ssl_ptr != last_ssl:
            generation[ssl_ptr] += 1
            key = (ssl_ptr, generation[ssl_ptr])
            last_ssl = ssl_ptr
        conn = by_connection.setdefault(key, {"in": [], "out": [], "all": []})
        for message in datagram.messages:
            conn["all"].append(message)
            if message.channel == 1:
                conn[datagram.dir].append((index, ts_ms, message))
    for number, conn in enumerate(by_connection.values(), 1):
        for direction in ("in", "out"):
            rows = conn[direction]
            if not rows:
                continue
            pieces, _ = reassemble_channel_messages(rows)
            if pieces:
                yield f"conn-{number:02d}/{direction}", b"".join(p["payload"] for p in pieces)


def scan_stream(label, stream):
    print(f"\n=== {label}: {len(stream)} reassembled channel-1 bytes")
    for name, needle in CANDIDATES.items():
        offsets = list(find_all(stream, needle))
        print(f"  {name}: {len(offsets)} occurrences")
        if len(offsets) < 3:
            continue
        offsets_hist = collections.Counter(o % 16 for o in offsets)
        print(f"    offset mod 16 histogram: {dict(sorted(offsets_hist.items()))}")
        gaps = collections.Counter(b - a for a, b in zip(offsets, offsets[1:]))
        print(f"    gap histogram (top 8): {gaps.most_common(8)}")
        hits = collections.Counter()
        total = 0
        for a, b in zip(offsets, offsets[1:]):
            gap = b - a
            total += 1
            for (shift, kind), value in declared_values(stream, a).items():
                if value is None:
                    continue
                for extra in range(0, 17):
                    if value == gap - extra:
                        hits[(shift, kind, extra)] += 1
        best = hits.most_common(5)
        print(f"    best declared-length matches over {total} gaps:")
        for (shift, kind, extra), count in best:
            print(f"      at +{shift} {kind} == gap-{extra}: {count}/{total}"
                  f" ({100.0 * count / total:.1f}%)")
        if not best:
            print("      none")
        print(f"    first segments ({min(6, len(offsets))}):")
        for a in offsets[:6]:
            end = min(a + 28, len(stream))
            print(f"      @{a} ({len(stream) - a} left): {stream[a:end].hex(' ')}")


def chain_test(stream, label, header=14, length_at=12, trailer=1, endian=">"):
    """Walk message to message using the declared length and verify the sequence counter.

    A frame is only real if the declared length lands exactly on the next header and the
    u32 LE counter right after the marker increments by one. Returns steps before the first
    break and the reason.
    """
    marker = b"\x00\x01\x08\x01"
    positions = list(find_all(stream, marker))
    if not positions:
        return None
    pos = positions[0]
    previous = None
    steps = 0
    reason = "end of stream"
    while True:
        if pos + header > len(stream):
            reason = "truncated_header"
            break
        seq = struct.unpack_from("<I", stream, pos + 4)[0]
        length = struct.unpack_from(endian + "H", stream, pos + length_at)[0]
        nxt = pos + header + length + trailer
        if previous is not None and seq != (previous + 1) & 0xFFFFFFFF:
            reason = f"sequence {previous} -> {seq} at {pos}"
            break
        if nxt + 4 > len(stream):
            reason = "end of stream"
            break
        if stream[nxt:nxt + 4] != marker:
            reason = (f"no header at {nxt} (len={length}); got "
                      f"{stream[nxt:nxt + 8].hex(' ')}")
            reason = reason[0] + reason[1]
            break
        previous = seq
        pos = nxt
        steps += 1
    reached = positions.index(pos) if pos in positions else -1
    print(f"    chain header={header} len@{length_at}{endian} trailer={trailer}: "
          f"{steps} steps, ended at occurrence #{reached}/{len(positions)}: {reason}")
    return steps


def chain_sweep(stream, label):
    print(f"  chain candidates for {label}:")
    best = None
    for header in (14, 12, 13, 15, 16):
        for length_at in (header - 2, header - 1):
            for trailer in (0, 1, 2):
                for endian in ("<", ">"):
                    steps = chain_test(stream, label, header, length_at, trailer, endian)
                    if steps is not None and (best is None or steps > best[0]):
                        best = (steps, header, length_at, trailer, endian)
    if best:
        print(f"  best chain: {best[0]} steps with header={best[1]} len@{best[2]}"
              f"{best[4]} trailer={best[3]}")
    return best


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("ledger", type=Path)
    args = parser.parse_args(argv)
    found = False
    for label, stream in channel_streams(args.ledger):
        scan_stream(label, stream)
        chain_sweep(stream, label)
        found = True
    if not found:
        print("no reassembled channel-1 stream in this ledger")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
