#!/usr/bin/env python3
"""Derive the payload length of every record type from a capture plus a record-layer probe log.

The record layer has no length field: each record is `[V1 varint][0x01][V2 varint][type
varint][flag][payload]` and the next record starts where the payload ends, so the length of a
record type can only be measured by knowing where two consecutive records start. This tool
gets those positions from a probe log (see `Tools/nw_capture/experimental/nw_record_probe.js`,
which hooks the readers that delimit records and logs the cursor windows) and resolves each
window to a stream offset, monotonically, so repeated windows do not become ambiguous.

    .venv-capture/bin/python Tools/nw_capture/experimental/offline/record_lengths.py \
        --log Tools/nw_capture/logs/<run>_<label>.log \
        --ledger Tools/nw_capture/captures/<run>/dtls/ledger.bin

Output: record count and the most frequent payload lengths per type index, which is what a
stream walker needs in order to skip a record of an unknown state instead of guessing.
"""
import argparse
import collections
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))

from decode_in_bodies import channel_stream  # noqa: E402
import decode_alc_state as D  # noqa: E402

V1_CALLER = "0x6af2134"


def header(data, offset):
    """(header length, type) of the record at offset, or None."""
    v1, n1 = D.read_mask_varint(data, offset)
    if not n1 or data[offset + n1] != 0x01:
        return None
    j = offset + n1 + 1
    v2, n2 = D.read_mask_varint(data, j)
    if not n2:
        return None
    j += n2
    kind, n3 = D.read_mask_varint(data, j)
    if not n3 or kind is None or kind > 8000:
        return None
    return n1 + 1 + n2 + n3 + 1, kind


def windows(log_path):
    out = []
    for line in open(log_path):
        try:
            entry = json.loads(line)
        except Exception:
            continue
        for item in entry.get("items") or []:
            if isinstance(item, list) and len(item) >= 8 and item[2] == V1_CALLER and item[5]:
                out.append(item[5])
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--top", type=int, default=14, help="how many types to print")
    args = parser.parse_args(argv)

    stream = channel_stream(str(args.ledger))
    positions, last, missing = [], 0, 0
    for text in windows(args.log):
        found = stream.find(bytes.fromhex(text), last)
        if found < 0:
            missing += 1
            positions.append(None)
            continue
        start = None
        for size in range(1, 6):
            if found - size < 1:
                break
            if D.read_mask_varint(stream, found - size)[1] == size and stream[found] == 0x01:
                start = found - size
                break
        positions.append(start)
        last = found + 1
    print(f"record positions: {sum(1 for p in positions if p is not None)} of {len(positions)} "
          f"({missing} windows not found)")

    by_type = collections.defaultdict(collections.Counter)
    for a, b in zip(positions, positions[1:]):
        if a is None or b is None or b <= a:
            continue
        total = b - a
        if not (2 < total < 8000):
            continue
        head = header(stream, a)
        if not head or head[0] >= total:
            continue
        by_type[head[1]][total - head[0]] += 1
    print("payload length per record type (most frequent first):")
    for kind in sorted(by_type, key=lambda k: -sum(by_type[k].values()))[:args.top]:
        print(f"  type {kind:>5}: {sum(by_type[kind].values()):>6} records | "
              f"payload bytes: {by_type[kind].most_common(5)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
