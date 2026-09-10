#!/usr/bin/env python3
"""Extract and track position candidates from inbound channel-1 bodies.

What is known from the code and the traces: the inbound bodies are cut by decode_in_bodies.py,
each record carries the type reference 11 (`ALCReplicatedState`), and the parser reads no raw
4-byte fields, so a position is not read as a plain float by the codec. Nevertheless the bodies
do contain float32 pairs in the game's world range, e.g. (15290.3, 4442.3), (15312.7, 2316.6),
(15226.3, 7899.3), (16345.8, 364.1) in the Test-teleport capture, stable over consecutive frames.

This tool extracts every plausible float32 pair from every framed body and links them across
frames by proximity, so the candidates become tracks. A real entity position shows up as a long
track whose consecutive values stay close, with a large step where the player teleports.

It is a screen, not a decoder: it prints what it found and how long it stayed consistent, and it
does not claim to know which track is the local player.

Usage:
    .venv-capture/bin/python Tools/nw_capture/experimental/offline/probe_position_candidates.py \
        Tools/nw_capture/captures/<session>/dtls/ledger.bin [--top 10] [--threshold 400]
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_CAPTURE_TOOL = _HERE.parents[1]
if str(_CAPTURE_TOOL) not in sys.path:
    sys.path.insert(0, str(_CAPTURE_TOOL))
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from decode_in_bodies import channel_stream, iter_frames  # noqa: E402

WORLD_LIMIT = 40000.0
MIN_ABS = 0.5


def plausible(value):
    return -WORLD_LIMIT < value < WORLD_LIMIT and abs(value) > MIN_ABS


def candidates_per_frame(bodies):
    for body in bodies:
        out = []
        for offset in range(0, max(0, len(body) - 8)):
            first = struct.unpack_from("<f", body, offset)[0]
            second = struct.unpack_from("<f", body, offset + 4)[0]
            if plausible(first) and plausible(second):
                out.append((offset, first, second))
        yield out


def track(frames, threshold, max_gap):
    tracks = []
    for frame_no, frame in enumerate(frames):
        used = set()
        for item in tracks:
            if frame_no - item["last"] > max_gap:
                continue
            best, best_distance = None, float("inf")
            for index, (offset, a, b) in enumerate(frame):
                if index in used:
                    continue
                distance = ((a - item["pos"][0]) ** 2 + (b - item["pos"][1]) ** 2) ** 0.5
                if distance < best_distance:
                    best_distance, best = distance, index
            if best is not None and best_distance <= threshold:
                offset, a, b = frame[best]
                used.add(best)
                if best_distance > 2000:
                    item["jumps"].append((frame_no, round(best_distance)))
                item["pos"] = (a, b)
                item["last"] = frame_no
                item["length"] += 1
                item["path"].append((frame_no, a, b))
        for index, (offset, a, b) in enumerate(frame):
            if index not in used:
                tracks.append({"pos": (a, b), "last": frame_no, "length": 1,
                               "path": [(frame_no, a, b)], "jumps": [], "offset": offset})
    return tracks


def summarize(tracks, top):
    tracks = sorted(tracks, key=lambda item: -item["length"])
    out = []
    for item in tracks[:top]:
        xs = [p[1] for p in item["path"]]
        ys = [p[2] for p in item["path"]]
        out.append({
            "length": item["length"],
            "offset": item["offset"],
            "first_frame": item["path"][0][0],
            "last_frame": item["path"][-1][0],
            "x_range": [min(xs), max(xs)],
            "y_range": [min(ys), max(ys)],
            "jumps": item["jumps"][:5],
            "head": [(round(p[1], 1), round(p[2], 1)) for p in item["path"][:5]],
        })
    return out


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("ledger", type=Path)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--threshold", type=float, default=400.0)
    parser.add_argument("--max-gap", type=int, default=5)
    args = parser.parse_args(argv)

    stream = channel_stream(args.ledger)
    bodies = [body for _, _, body, _ in iter_frames(stream)]
    frames = list(candidates_per_frame(bodies))
    total = sum(len(frame) for frame in frames)
    tracks = track(frames, args.threshold, args.max_gap)
    print(f"ledger: {args.ledger}")
    print(f"  framed bodies: {len(bodies)}")
    print(f"  plausible float pairs: {total}")
    print(f"  tracks: {len(tracks)}")
    for item in summarize(tracks, args.top):
        print(f"  len={item['length']:4d} offset={item['offset']:3d} "
              f"frames {item['first_frame']}..{item['last_frame']} "
              f"x=[{item['x_range'][0]:.0f},{item['x_range'][1]:.0f}] "
              f"y=[{item['y_range'][0]:.0f},{item['y_range'][1]:.0f}] jumps={item['jumps']}")
        print(f"      head={item['head']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
