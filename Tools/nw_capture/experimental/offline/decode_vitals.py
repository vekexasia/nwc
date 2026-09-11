#!/usr/bin/env python3
"""Read entity health (and the vitals update that carries it) out of a capture.

The Vitals payload carries one `[member mask][field mask][fields]` block per member that changed,
in the state's member order, and member 0 is `HealthAmount` (`+0x7c0`). Its field mask bit 0 is the
**big-endian float32** current health, which is what this reads:

```
01 01 46 1b 88 f3      member 0 present, field bit 0: health 9954.2
01 09 46 17 75 cb 03   member 0, field bits 0 and 3: health plus one byte
```

Verified on a drain capture: the decoded deltas were +57.7 and -362.4 on the object that produced
the player's own combat text (+57 heal, 362 damage), which is what identifies the player's entity in
a capture. Reproduced on a second capture (a -362.4 drop inside the drain window, +57.7 and +43.9
between drops).

    .venv-capture/bin/python Tools/nw_capture/experimental/offline/decode_vitals.py \
        --log Tools/nw_capture/logs/<run>_drain.log --object 0x3d5bac00

The log comes from `nw_state_probe.js` (it records object, consumed bytes and the payload).
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import struct
from pathlib import Path

TAG = "Vitals-stage-90-mask"
MEMBER_HEALTH = 0x01   # member mask: member 0 (HealthAmount) is present
FIELD_HEALTH = 0x01    # its field mask: bit 0 is the float32


def parse_members(payload: bytes):
    """Decode what is known of one Vitals payload.

    Returns a dict with any of ``health`` and ``mana`` that the payload carries, and an empty dict
    when the payload does not use a shape we have evidence for. It never guesses: an unknown member
    mask, field mask or ordering stops the walk and returns what was already decoded.
    """
    out = {}
    index = 0
    while index < len(payload):
        member_mask = payload[index]
        index += 1
        if member_mask == 0:
            continue
        for bit in range(8):
            if not member_mask >> bit & 1:
                continue
            if index >= len(payload):
                return out
            field_mask = payload[index]
            index += 1
            if bit == 0:
                if field_mask & FIELD_HEALTH:
                    if index + 4 > len(payload):
                        return out
                    value = struct.unpack(">f", payload[index:index + 4])[0]
                    if math.isfinite(value):
                        out["health"] = value
                    index += 4
                if field_mask & 0x08:
                    if index >= len(payload):
                        return out
                    index += 1
                if field_mask & ~0x09:
                    return out
            elif bit == 1:
                if field_mask & FIELD_HEALTH:
                    if index + 4 > len(payload):
                        return out
                    value = struct.unpack(">f", payload[index:index + 4])[0]
                    if math.isfinite(value):
                        out["mana"] = value
                    index += 4
                if field_mask & ~0x01:
                    return out
            else:
                return out
        if member_mask & ~0x03:
            return out
    return out if index == len(payload) else out


def parse_full_state(payload: bytes):
    """The Vitals full state (member 0 with field mask ff, then a second ff mask byte for fields 8..15).

    Read across players, pets and mobs of one capture (docs/NEXT_SESSION.md 2026-09-11 night):

        0..1   member mask (01 or 03 for the owner), field mask ff
        2..5   f32 health                      6..9   f32 100/110 on players, 0 on pets and mobs
        10     u8   11 u8 (0b)                 12..19 u64 (a time stamp)
        20..23 u32  24..25 u16  26 u8          27     second field mask, ff
        28     u8                              29..32 f32 HealthBaseMax: equals the max health of every
                                                       mob checked (Grey Wolf 609, Turkey 16, Boar 639,
                                                       Withered 548); for players the live max is above it
        33..34 u16  35..38 f32 (100 players, 1.0 mobs: mana base max)  39..41 three u8
        42..45 vitalsId crc32, 46..49 vitalsCategoryId crc32 (mobs; players carry 'Player' + 4 bytes)
        50..53 u32 vitalsLevel, 54..55 u16 flags (mobs only: 56-byte payloads)
    """
    if len(payload) < 42 or payload[1] != 0xFF or payload[27] != 0xFF or not payload[0] & 1:
        return {}
    out = {"health": struct.unpack(">f", payload[2:6])[0], "field1": struct.unpack(">f", payload[6:10])[0],
           "health_base_max": struct.unpack(">f", payload[29:33])[0], "vitals_id": payload[42:46].hex()}
    if len(payload) == 56:
        out["vitals_category_id"] = payload[46:50].hex()
        out["level"] = struct.unpack(">I", payload[50:54])[0]
    return out if all(math.isfinite(v) for v in (out["health"], out["health_base_max"])) else {}


def samples(log_path: Path, per_object: bool = True):
    """Yield (ts, object, health, payload) for every payload that carries the health field."""
    out = collections.defaultdict(list) if per_object else []
    for line in open(log_path):
        try:
            entry = json.loads(line)
        except Exception:
            continue
        for item in entry.get("items") or []:
            if not isinstance(item, list) or len(item) < 5 or item[1] != TAG:
                continue
            ts, payload_hex = item[0], item[4]
            if not payload_hex:
                continue
            payload = bytes.fromhex(payload_hex)
            decoded = parse_members(payload)
            if "health" not in decoded:
                continue
            health = decoded["health"]
            if per_object:
                out[item[3]].append((ts, round(health, 1), payload))
            else:
                out.append((ts, item[3], round(health, 1), payload))
    return out


def report(per_object) -> None:
    print(f"oggetti con la vita nel payload: {len(per_object)}")
    rows = []
    for obj, samples_ in per_object.items():
        values = [v for _, v, _ in samples_]
        deltas = [round(b - a, 1) for a, b in zip(values, values[1:]) if abs(b - a) > 0.5]
        rows.append((len(samples_), obj, values, deltas))
    for count, obj, values, deltas in sorted(rows, reverse=True)[:10]:
        seq = []
        for value in values:
            if not seq or seq[-1] != value:
                seq.append(value)
        print(f"  {obj}: {count} campioni | valori distinti: {seq[:12]}")
        if deltas:
            print(f"      salti: {deltas[:12]}")


def self_check() -> int:
    """The four payloads that were verified against the game's own combat text."""
    cases = [
        ("0101461aa210", 9896.5),
        ("0101461b88f3", 9954.2),
        ("01014615df53", 9591.8),
        ("0109461775cb03", 9693.4),
    ]
    for payload_hex, expected in cases:
        payload = bytes.fromhex(payload_hex)
        got = struct.unpack(">f", payload[2:6])[0]
        assert abs(got - expected) < 0.1, (payload_hex, got, expected)
    nan_health = bytes([0x01, 0x01]) + struct.pack(">f", float("nan"))
    assert "health" not in parse_members(nan_health), "a NaN health must not be decoded as a value"
    assert round(9954.2 - 9896.5, 1) == 57.7      # the heal the player saw as +57
    assert round(9954.2 - 9591.8, 1) == 362.4     # the drain the player saw as 362
    wolf = parse_full_state(bytes.fromhex("01ff4418400000000000000bb0f5d4ffcea7c90000000000000000ff004418400000003f8000004f0000d69ee7124f97b6a8000000060261"))   # Grey Wolf e159, live3 log
    assert wolf and wolf["health_base_max"] == 609.0 and wolf["level"] == 6 and wolf["vitals_id"] == "d69ee712", wolf
    print("self-check ok: quattro payload verificati e i due delta di riferimento")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--log", type=Path)
    parser.add_argument("--object", help="only this object address")
    parser.add_argument("--check", action="store_true", help="run the self-check and exit")
    args = parser.parse_args(argv)
    if args.check:
        return self_check()
    if not args.log:
        parser.error("--log or --check is required")
    per_object = samples(args.log)
    if args.object:
        per_object = {k: v for k, v in per_object.items() if k == args.object}
    report(per_object)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
