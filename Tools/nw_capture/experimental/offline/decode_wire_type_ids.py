#!/usr/bin/env python3
"""Resolve the type identifiers carried on the wire to registry entries and names.

What is verified, and how:

  * The inbound parser reads, at one specific position, a prefix-coded varint through the
    reader at RVA 0x61ad00f (function `FUN_1461acfe0`): a value of 0 means "16 raw bytes
    follow", any other value is an index into a table. Measured on a live capture:
    every value observed there is inside the live registry's `typeIndex` space (0..7051).
  * The registry (`/tmp/nwc/live-registry.json`, dumped read-only from the running process)
    maps typeIndex -> index -> uuid. The most frequent observed value is typeIndex 11, uuid
    01B0664B-3AB6-44A6-87E3-8C69D40E0365, registry index 1075.
  * That uuid's name only exists in a static descriptor in the binary: at file offset
    0x80fd468 sits the ASCII uuid, and uuid_offset - 0xA8 holds a pointer to the string
    "ALCReplicatedState" (verified byte for byte). This script generalises that lookup: for
    every observed uuid it searches the executable for the dashed uuid string and tests the
    same descriptor layout for a name pointer.

Names are only available where such a descriptor exists, so most ids come back with
`name: null`; the uuid and registry index are still concrete.

Usage:
    .venv-capture/bin/python Tools/nw_capture/experimental/offline/decode_wire_type_ids.py \
        --trace Tools/nw_capture/logs/<run>_uuid_refs.log \
        --registry /tmp/nwc/live-registry.json \
        [--exe "$HOME/.local/share/Steam/steamapps/common/New World/Bin64/NewWorld.exe"] \
        [--json out.json]
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import struct
from pathlib import Path

DEFAULT_EXE = Path.home() / ".local/share/Steam/steamapps/common/New World/Bin64/NewWorld.exe"
SECTIONS = ((0x147ec9000, 0x7ec7800, 0x01fb151e), (0x149e7b000, 0x9e78e00, 0x00467000))
NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(::[A-Za-z_][A-Za-z0-9_]*)*$")
DESCRIPTOR_DELTAS = (0xA8, 0xA0, 0xB0, 0x98)


def observed_ids_from_trace(path):
    """Collect the values read by the 16-byte reference reader from a uuid_refs trace log."""
    counts = collections.Counter()
    with Path(path).open(encoding="utf-8") as handle:
        return _collect_ids(handle, counts)


def _collect_ids(handle, counts):
    for line in handle:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if record.get("type") != "uuid_refs":
            continue
        for _ts, kind, value, _ptr, _hex in record.get("items", []):
            if kind == "idx":
                counts[value] += 1
    return counts


def va_to_offset(va):
    for base, raw, size in SECTIONS:
        if base <= va < base + size:
            return raw + (va - base)
    return None


def name_for_uuid(data, uuid):
    """Look for the static descriptor whose name pointer precedes the uuid string."""
    for needle in (uuid.lower().encode(), uuid.upper().encode()):
        start = 0
        while True:
            index = data.find(needle, start)
            if index < 0:
                break
            start = index + 1
            for delta in DESCRIPTOR_DELTAS:
                record = index - delta
                if record < 8:
                    continue
                pointer = struct.unpack_from("<Q", data, record)[0]
                if not (0x140000000 <= pointer < 0x160000000):
                    continue
                offset = va_to_offset(pointer)
                if offset is None:
                    continue
                end = data.find(b"\0", offset)
                candidate = data[offset:min(end, offset + 96)]
                if not (3 <= len(candidate) <= 96):
                    continue
                try:
                    text = candidate.decode("ascii")
                except UnicodeDecodeError:
                    continue
                if NAME_RE.match(text) and len(text) > 4:
                    return text
    return None


def resolve(counts, registry, exe_path=None):
    by_type = {entry["typeIndex"]: entry for entry in registry["entries"]}
    data = exe_path.read_bytes() if exe_path and exe_path.exists() else None
    rows = []
    for value, count in counts.most_common():
        entry = by_type.get(value)
        row = {
            "typeIndex": value,
            "count": count,
            "in_registry": entry is not None,
            "registryIndex": entry["index"] if entry else None,
            "uuid": entry["uuid"] if entry else None,
            "name": (entry.get("name") or entry.get("communityName") or "") if entry else "",
        }
        if not row["name"] and data and row["uuid"]:
            row["name"] = name_for_uuid(data, row["uuid"]) or ""
        rows.append(row)
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", type=Path, required=True,
                        help="uuid_refs trace log from probe_uuid_refs.js")
    parser.add_argument("--registry", type=Path, required=True,
                        help="live registry JSON (typeIndex/index/uuid/name per entry)")
    parser.add_argument("--exe", type=Path, default=DEFAULT_EXE)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)

    counts = observed_ids_from_trace(args.trace)
    if not counts:
        print("no id events in the trace")
        return 1
    registry = json.loads(args.registry.read_text())
    rows = resolve(counts, registry, args.exe)
    inside = sum(1 for row in rows if row["in_registry"])
    named = sum(1 for row in rows if row["name"])
    print(f"observed identifiers: {len(rows)} distinct, {sum(counts.values())} events")
    print(f"  inside the registry typeIndex space: {inside}/{len(rows)}")
    print(f"  resolved to a name: {named}/{len(rows)}")
    print(f"\n{'typeIndex':>9} {'count':>7} {'index':>7}  name")
    for row in rows:
        index = row["registryIndex"] if row["registryIndex"] is not None else -1
        print(f"{row['typeIndex']:>9} {row['count']:>7} {index:>7}  {row['name'] or '<no name>'}")
    if args.json:
        args.json.write_text(json.dumps(rows, indent=1))
        print(f"\njson: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
