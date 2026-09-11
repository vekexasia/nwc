"""Census of the ALC slayer state ids in a join log, with the context that hints at their meaning.

For every (layer, state id): how many entities showed it, how many of them are players (they carry a
PlayerComponent chunk), how often the entity was mounted at that moment, and its median ground speed
in the next second (from worldPosAbs). Names in decode_pose.LAYER_NAMES are printed next to the id;
the rest is what the table is for: reading a name off the context, then driving one action to prove it.

    pose_census.py --log Tools/nw_capture/logs/<run>.log [--layer 0] [--min 5]
"""
import argparse
import statistics
import struct
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from decode_alc_state import decode_record_payload  # noqa: E402
from decode_join import log_items  # noqa: E402
from decode_mount import parse_mount  # noqa: E402
from decode_pose import LAYER_NAMES, pose_from_payload  # noqa: E402


def census(items, min_count):
    players, mounted, positions, events = set(), {}, defaultdict(list), []
    for ts, v1, _v2, type_index, _obj, length, payload_hex in (it[:7] for it in items):
        if type_index == 3935:
            players.add(v1)
        elif type_index == 5620:
            decoded = parse_mount(bytes.fromhex(payload_hex))
            if "mounted" in decoded:
                mounted[v1] = decoded["mounted"]
        elif type_index == 11 and len(payload_hex) == 2 * length:
            payload = bytes.fromhex(payload_hex)
            decoded = pose_from_payload(payload)
            for layer, value in decoded.get("pose", {}).items():
                events.append((ts, v1, layer, value["id"], mounted.get(v1, False)))
            fields, _used = decode_record_payload(payload, 0)
            for _bit, name, chunk, _v in fields or []:
                if name == "worldPosAbs" and len(chunk) == 10:
                    x, y, _e = struct.unpack(">ffH", chunk)
                    positions[v1].append((ts, x, y))
    speeds = defaultdict(list)
    for ts, v1, layer, state_id, _m in events:
        track = positions.get(v1, [])
        after = [(t, x, y) for t, x, y in track if ts <= t <= ts + 1500]
        if len(after) >= 2:
            (t0, x0, y0), (t1, x1, y1) = after[0], after[-1]
            if t1 > t0:
                speeds[(layer, state_id)].append(((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5 / ((t1 - t0) / 1000))
    table = defaultdict(lambda: {"n": 0, "entities": set(), "players": set(), "mounted": 0})
    for ts, v1, layer, state_id, is_mounted in events:
        row = table[(layer, state_id)]
        row["n"] += 1
        row["entities"].add(v1)
        if v1 in players:
            row["players"].add(v1)
        row["mounted"] += is_mounted
    rows = []
    for (layer, state_id), row in table.items():
        if row["n"] < min_count:
            continue
        speed = speeds.get((layer, state_id), [])
        rows.append((layer, state_id, row["n"], len(row["entities"]), len(row["players"]),
                     row["mounted"] / row["n"], statistics.median(speed) if speed else None,
                     LAYER_NAMES.get(layer, {}).get(state_id, "")))
    return sorted(rows, key=lambda r: (r[0], -r[2]))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--layer", type=int)
    parser.add_argument("--min", type=int, default=5, help="minimum transitions for a row")
    args = parser.parse_args(argv)
    rows = census(log_items(args.log.read_text(errors="ignore").splitlines()), args.min)
    print("layer  id     transitions entities players mounted%  speed(u/s)  name")
    for layer, state_id, n, ents, players, mounted, speed, name in rows:
        if args.layer is not None and layer != args.layer:
            continue
        speed_text = "-" if speed is None else f"{speed:5.1f}"
        print(f"L{layer}     {state_id:#06x} {n:11d} {ents:8d} {players:7d} {100 * mounted:7.0f}%  {speed_text:>10}  {name}")


if __name__ == "__main__":
    main()
