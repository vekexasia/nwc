#!/usr/bin/env python3
"""S2 probe: do the channel-1 message bodies carry resolvable type identifiers?

Cuts messages with the S1 frame (marker 00 01 08 01 + u32 LE counter + 4 bytes +
u16 BE length + body + 1..3 trailer bytes), then looks at which 32-bit values recur in
the bodies and whether any of them resolves in the private registries:

  * private/open-world-discord/attachments/128_serialize.json  (classNameToUuid: crc -> uuid,
    uuidMap: uuid -> name)
  * private/open-world-discord/attachments/087_typeregistry.json (index, typeIndex, name, uuid)

Read-only. Prints counts only; no payload dumps beyond short hex heads.
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

REPO = Path(__file__).resolve().parents[4]
ATTACH = REPO / "private" / "open-world-discord" / "attachments"
MARKER = b"\x00\x01\x08\x01"


def find_all(data, needle):
    start = 0
    while True:
        offset = data.find(needle, start)
        if offset < 0:
            return
        yield offset
        start = offset + 1


def channel_stream(ledger_path):
    last_ssl = None
    generation = collections.Counter()
    key = None
    groups = collections.OrderedDict()
    for index, dir_byte, ts_ms, ssl_ptr, payload in iter_ledger(ledger_path):
        datagram = decode_record(index, dir_byte, ts_ms, ssl_ptr, payload)
        if ssl_ptr != last_ssl:
            generation[ssl_ptr] += 1
            key = (ssl_ptr, generation[ssl_ptr])
            last_ssl = ssl_ptr
        if datagram.dir != "in":
            continue
        bucket = groups.setdefault(key, [])
        for message in datagram.messages:
            if message.channel == 1:
                bucket.append((index, ts_ms, message))
    for rows in groups.values():
        pieces, _ = reassemble_channel_messages(rows)
        if pieces:
            return b"".join(p["payload"] for p in pieces)
    return b""


def cut_frames(stream):
    """Yield (offset, body) for every message whose declared length closes the frame."""
    positions = list(find_all(stream, MARKER))
    accepted = rejected = 0
    frames = []
    for a, b in zip(positions, positions[1:]):
        length = struct.unpack_from(">H", stream, a + 12)[0]
        body_start = a + 14
        for trailer in (1, 2, 3):
            if body_start + length + trailer == b:
                frames.append((a, stream[body_start:body_start + length]))
                accepted += 1
                break
        else:
            rejected += 1
    return frames, accepted, rejected, len(positions)


def load_registries():
    ser = json.load(open(ATTACH / "128_serialize.json", encoding="utf-8"))
    uuid_to_name = {}
    for uuid, entry in ser["uuidMap"].items():
        if entry.get("name"):
            uuid_to_name[uuid] = entry["name"]
    crc_to_uuid = {}
    for crc, uuid in ser["classNameToUuid"]:
        crc_to_uuid[crc & 0xFFFFFFFF] = uuid
    reg = json.load(open(ATTACH / "087_typeregistry.json", encoding="utf-8"))
    by_index = {}
    by_type_index = {}
    by_uuid = {}
    for entry in reg["data"]["m_list"]:
        body = entry[1] if isinstance(entry, list) else entry
        if not isinstance(body, dict):
            continue
        if isinstance(body.get("index"), int):
            by_index[body["index"]] = body.get("name")
        if isinstance(body.get("typeIndex"), int):
            by_type_index[body["typeIndex"]] = body.get("name")
        if body.get("uuid"):
            by_uuid[body["uuid"]] = body.get("name")
    return {
        "uuid_to_name": uuid_to_name,
        "crc_to_uuid": crc_to_uuid,
        "by_index": by_index,
        "by_type_index": by_type_index,
        "by_uuid": by_uuid,
    }


def u32_histogram(frames, skip=0, limit=None):
    hist = collections.Counter()
    for offset, body in frames[:limit]:
        for i in range(skip, len(body) - 3):
            hist[struct.unpack_from("<I", body, i)[0]] += 1
    return hist


def resolve(value, reg):
    hits = []
    uuid = reg["crc_to_uuid"].get(value)
    if uuid:
        hits.append(f"serialize.crc->{uuid}->{reg['uuid_to_name'].get(uuid, '?')}")
    if value in reg["by_index"]:
        hits.append(f"typeregistry.index->{reg['by_index'][value]}")
    if value in reg["by_type_index"]:
        hits.append(f"typeregistry.typeIndex->{reg['by_type_index'][value]}")
    return hits


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("ledger", type=Path)
    parser.add_argument("--u32-every-byte", action="store_true",
                        help="histogram u32 at every byte offset (default: only offset 0)")
    args = parser.parse_args(argv)

    stream = channel_stream(args.ledger)
    if not stream:
        print("no reassembled IN channel-1 stream")
        return 1
    frames, accepted, rejected, markers = cut_frames(stream)
    print(f"stream {len(stream)} bytes, {markers} markers, {accepted} framed, {rejected} rejected")
    if not frames:
        return 1
    print("\nfirst 6 bodies:")
    for offset, body in frames[:6]:
        print(f"  @{offset} len={len(body):5d}: {body[:26].hex(' ')}")

    reg = load_registries()
    print(f"\nregistries: {len(reg['crc_to_uuid'])} crc->uuid, "
          f"{len(reg['by_index'])} index, {len(reg['by_type_index'])} typeIndex")

    print("\nu32 at body offset 0 (top 12):")
    hist0 = u32_histogram(frames, skip=0, limit=0) if False else None
    head = collections.Counter(struct.unpack_from("<I", body, 0)[0]
                               for _, body in frames if len(body) >= 4)
    for value, count in head.most_common(12):
        hits = resolve(value, reg)
        print(f"  {value:>10} 0x{value:08x} x{count:<6} {hits if hits else ''}")

    if args.u32_every_byte:
        print("\nu32 at every offset (top 15, with resolution):")
        hist = u32_histogram(frames)
        for value, count in hist.most_common(15):
            hits = resolve(value, reg)
            print(f"  {value:>10} 0x{value:08x} x{count:<6} {hits if hits else ''}")

    u16 = collections.Counter()
    for _, body in frames:
        for i in range(0, len(body) - 1, 2):
            u16[struct.unpack_from("<H", body, i)[0]] += 1
    in_range = sum(c for v, c in u16.items() if v <= 3486)
    total = sum(u16.values())
    print(f"\nu16 at even body offsets: {len(u16)} distinct, {100*in_range/max(1,total):.1f}% "
          f"of {total} values fall inside the typeregistry index range 0..3486")
    print("  values above the index range (top 5):")
    for value, count in u16.most_common(400):
        if value > 3486:
            print(f"    {value:>6} x{count} {reg['by_index'].get(value, '')}")
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
