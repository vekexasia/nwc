#!/usr/bin/env python3
"""Hunt for coordinate-like slots in inbound channel-1 bodies.

Idea: if an inbound replicated state carries a world position, then somewhere in the body
there are three float32 values that (a) sit in the world's numeric range, and (b) change
smoothly from message to message while the player moves, with a large jump when the player
teleports. Nothing here assumes the body grammar: it scores every byte offset of every
record payload as a candidate float slot, and reports only the slots that survive the
smoothness test.

This is a hypothesis screen, not a decoder: a slot has to beat chance, and its evidence is
reported (sample count, range, deltas, largest jump) so the claim can be checked by hand.

Usage:
    .venv-capture/bin/python Tools/nw_capture/experimental/offline/probe_position_hunt.py \
        Tools/nw_capture/captures/<session>/dtls/ledger.bin [--top 10]
"""
from __future__ import annotations

import argparse
import collections
import json
import struct
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_CAPTURE_TOOL = _HERE.parents[1]
if str(_CAPTURE_TOOL) not in sys.path:
    sys.path.insert(0, str(_CAPTURE_TOOL))
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from decode_in_bodies import channel_stream, iter_frames, split_records  # noqa: E402

WORLD_LIMIT = 60000.0       # reject absurd floats
MIN_ABS = 0.001             # reject zeros/denormals
MAX_STEP = 800.0            # a moving player does not jump 800 world units per message
MIN_SAMPLES = 25


def float_slots(body_series):
    """Yield candidate series: {(record_index, offset): [(frame_no, value)]}."""
    series = collections.defaultdict(list)
    for frame_no, records in body_series:
        for record_index, (_, _, payload) in enumerate(records):
            for offset in range(0, max(0, len(payload) - 3)):
                value = struct.unpack_from("<f", payload, offset)[0]
                if value != value:                      # NaN
                    continue
                if abs(value) > WORLD_LIMIT or abs(value) < MIN_ABS:
                    continue
                series[(record_index, offset)].append((frame_no, value))
    return series


def score(entries):
    values = [v for _, v in entries]
    if len(values) < MIN_SAMPLES:
        return None
    steps = [abs(b - a) for (_, a), (_, b) in zip(entries, entries[1:])]
    smooth = sum(1 for s in steps if s < MAX_STEP)
    if not steps:
        return None
    return {
        "samples": len(values),
        "smooth_fraction": smooth / len(steps),
        "min": min(values),
        "max": max(values),
        "mean": sum(values) / len(values),
        "largest_step": max(steps),
        "largest_step_index": steps.index(max(steps)),
    }


def analyze(ledger_path, top=10, limit=None):
    stream = channel_stream(ledger_path)
    bodies = []
    for frame_no, (_, _, body, _) in enumerate(iter_frames(stream)):
        _, records, _ = split_records(body)
        if records:
            bodies.append((frame_no, records))
        if limit is not None and frame_no >= limit:
            break
    series = float_slots(bodies)
    scored = []
    for key, entries in series.items():
        result = score(entries)
        if result is None:
            continue
        if result["smooth_fraction"] < 0.90:
            continue
        if result["max"] - result["min"] < 1.0:
            continue
        scored.append((key, result, entries))
    scored.sort(key=lambda item: (-item[1]["samples"], item[1]["largest_step"]))
    return {
        "ledger": str(ledger_path),
        "frames_with_records": len(bodies),
        "candidate_slots_total": len(series),
        "candidates_passing": len(scored),
        "top": [
            {
                "slot": {"record_index": key[0], "payload_offset": key[1]},
                "stats": stats,
                "first_values": [round(v, 3) for _, v in entries[:12]],
            }
            for key, stats, entries in scored[:top]
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("ledger", type=Path)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)
    result = analyze(args.ledger, args.top, args.limit)
    print(f"ledger: {result['ledger']}")
    print(f"  frames with records: {result['frames_with_records']}")
    print(f"  candidate slots: {result['candidate_slots_total']}, "
          f"passing the smoothness screen: {result['candidates_passing']}")
    for item in result["top"]:
        slot = item["slot"]
        stats = item["stats"]
        print(f"  record #{slot['record_index']} payload+{slot['payload_offset']}: "
              f"n={stats['samples']} smooth={stats['smooth_fraction']:.2f} "
              f"range=[{stats['min']:.2f}, {stats['max']:.2f}] "
              f"largest_step={stats['largest_step']:.2f}@{stats['largest_step_index']}")
        print(f"      first values: {item['first_values']}")
    if args.json:
        args.json.write_text(json.dumps(result, indent=1))
        print(f"json: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
