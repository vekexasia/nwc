#!/usr/bin/env python3
"""Decode the player position out of the ALCReplicatedState wire fields.

Where this comes from (all verified statically on this build, see
docs/Network/offline-framing-findings.md):

  * `FUN_142a3b050` is the ALC type factory: it allocates the type named
    "ALCReplicatedState" and builds its property schema with `FUN_142a35db0`, which registers 48
    ordered properties. Two of them are the position:
      worldPosAbs  -> reader 0x142a433d0, 10 wire bytes: two byte-swapped float32 + one quantised u16
      worldPosRel  -> reader 0x142a43330,  3 wire bytes: three quantised deltas, 0xff = "no update"
  * The absolute reader reads each u32 through `FUN_146167960`, an import thunk that converts
    network order to host order, so the two floats are big-endian on the wire.
  * The third component is a u16 quantised into the range [-100, 1000] (the code multiplies by
    1/65535 and adds the range base). Big-endian is the order that yields a stable value for a
    standing entity; little-endian oscillates.

This tool consumes the samples produced by `nw_pos_probe.js` (one JSON event per sample) and emits
the decoded positions, so a capture can be re-analysed without the game:

    .venv-capture/bin/python Tools/nw_capture/experimental/decode_position.py \
        --log Tools/nw_capture/logs/<run>_pos.log --json /tmp/positions.json [--csv /tmp/positions.csv]

It prints the track summary (per entity, by position clustering) and the movement steps, which is
how the decode was validated: while the operator walked, x advanced monotonically by ~2 units per
update and z stayed put.
"""
from __future__ import annotations

import argparse
import collections
import json
import struct
import sys
from pathlib import Path

Y_MIN, Y_SPAN = -100.0, 1100.0      # range constants of the quantised third component


def decode_abs(raw: bytes):
    """10 wire bytes -> (x, z, y). Two big-endian float32 then a big-endian quantised u16."""
    if len(raw) != 10:
        return None
    x = struct.unpack(">f", raw[0:4])[0]
    z = struct.unpack(">f", raw[4:8])[0]
    q = int.from_bytes(raw[8:10], "big")
    y = Y_MIN + q * Y_SPAN / 65535.0
    return x, z, y


def decode_rel(raw: bytes):
    """3 wire bytes -> deltas. 0xff means 'no update' for that component."""
    if len(raw) != 3:
        return None
    return tuple(0.0 if b == 0xFF else (2.0 * b / 255.0 - 1.0) for b in raw)


def load_samples(path):
    samples = []
    with Path(path).open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if record.get("type") != "pos_samples":
                continue
            for ts, tag, hexs, _cursor in record.get("items", []):
                samples.append((ts, tag, hexs))
    samples.sort()
    return samples


def build_tracks(points, time_gap_ms=3000, distance=400.0):
    """Cluster absolute samples into per-entity tracks by position and time proximity."""
    tracks = []
    for ts, x, z, y in points:
        for track in tracks:
            if ts - track["last_ts"] < time_gap_ms and abs(x - track["x"]) < distance \
                    and abs(z - track["z"]) < distance:
                track["points"].append((ts, x, z, y))
                track["x"], track["z"], track["y"], track["last_ts"] = x, z, y, ts
                break
        else:
            tracks.append({"points": [(ts, x, z, y)], "x": x, "z": z, "y": y, "last_ts": ts})
    return sorted(tracks, key=lambda t: -len(t["points"]))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--log", required=True, type=Path, help="pos_samples log from nw_pos_probe.js")
    parser.add_argument("--json", type=Path, help="write the decoded samples here")
    parser.add_argument("--csv", type=Path, help="write 'ts,x,y,z' rows here (absolute samples only)")
    parser.add_argument("--top", type=int, default=3, help="how many tracks to summarise")
    args = parser.parse_args(argv)

    samples = load_samples(args.log)
    if not samples:
        print("no pos_samples in that log", file=sys.stderr)
        return 1
    absolute, relatives, decoded = [], [], []
    for ts, tag, hexs in samples:
        raw = bytes.fromhex(hexs)
        if tag == "ABS":
            value = decode_abs(raw)
            if value is None:
                continue
            x, z, y = value
            absolute.append((ts, x, z, y))
            decoded.append({"ts": ts, "kind": "abs", "x": round(x, 3), "y": round(y, 3),
                            "z": round(z, 3), "raw": hexs})
        elif tag == "REL":
            value = decode_rel(raw)
            if value is None:
                continue
            relatives.append((ts, value))
            decoded.append({"ts": ts, "kind": "rel", "dx": round(value[0], 4),
                            "dy": round(value[1], 4), "dz": round(value[2], 4), "raw": hexs})

    print(f"samples: {len(samples)}  absolute: {len(absolute)}  relative: {len(relatives)}")
    tracks = build_tracks(absolute)
    print(f"tracks: {len(tracks)}")
    for index, track in enumerate(tracks[:args.top], 1):
        points = track["points"]
        xs = [p[1] for p in points]
        zs = [p[2] for p in points]
        ys = [p[3] for p in points]
        steps = [round(b[1] - a[1], 3) for a, b in zip(points, points[1:]) if b[1] != a[1]]
        print(f"  track {index}: {len(points)} samples  x[{min(xs):.2f}..{max(xs):.2f}] "
              f"z[{min(zs):.2f}..{max(zs):.2f}] y[{min(ys):.2f}..{max(ys):.2f}]")
        print(f"      x steps (non-zero): {steps[:10]}{' ...' if len(steps) > 10 else ''}")
        print(f"      first: x={points[0][1]:.3f} z={points[0][2]:.3f} y={points[0][3]:.3f}   "
              f"last: x={points[-1][1]:.3f} z={points[-1][2]:.3f} y={points[-1][3]:.3f}")
    if args.json:
        args.json.write_text(json.dumps(decoded, indent=1))
        print(f"json: {args.json}")
    if args.csv:
        with args.csv.open("w", encoding="utf-8") as handle:
            handle.write("ts,x,y,z\n")
            for ts, x, z, y in absolute:
                handle.write(f"{ts},{x:.3f},{y:.3f},{z:.3f}\n")
        print(f"csv: {args.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
