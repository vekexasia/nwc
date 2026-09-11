"""Group the chunks logged by nw_join_probe.js by their record header V1.

Each ``join_samples`` item is ``[ts, v1, v2, typeIndex, object, payload_len, payload_hex, name?]``.
ALC (11) payloads give the position, Vitals (15) the health, PlayerComponent (3935) the name. If
one V1 carries all three for the same entity, V1 is the join key the live view lacks.

    decode_join.py --log Tools/nw_capture/logs/<run>_join.log
    decode_join.py --check
"""
import argparse
import json
import struct
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from decode_alc_state import decode_record_payload  # noqa: E402
from decode_vitals import parse_members  # noqa: E402

ALC, VITALS, PLAYER = 11, 15, 3935
LENGTHS = {}   # typeIndex -> payload lengths seen: the record-length oracle, exact per chunk


def entities(lines):
    """Return {v1: {"types": {typeIndex: count}, "objects": {typeIndex: set}, "pos", "health", "name"}}."""
    out = defaultdict(lambda: {"types": defaultdict(int), "objects": defaultdict(set), "pos": [],
                               "health": None, "name": None, "v2": set()})
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get("type") != "join_samples":
            continue
        for item in entry.get("items", []):
            _ts, v1, v2, type_index, obj, length, payload_hex = item[:7]
            slot = out[v1]
            slot["types"][type_index] += 1
            slot["objects"][type_index].add(obj)
            slot["v2"].add(v2)
            lengths = LENGTHS.setdefault(type_index, [])
            if len(lengths) < 10000:
                lengths.append(length)
            payload = bytes.fromhex(payload_hex)
            if type_index == ALC and len(payload) == length:
                fields, used = decode_record_payload(payload, 0)
                if fields is None or used != length:
                    slot["types"]["alc_inexact"] += 1
                    continue
                for _bit, name, chunk, _value in fields:
                    if name == "worldPosAbs" and len(chunk) == 10:
                        x, y, elevation = struct.unpack(">ffH", chunk)
                        slot["pos"].append((round(x, 2), round(y, 2), elevation))
            elif type_index == VITALS:
                decoded = parse_members(payload)
                if "health" in decoded:
                    slot["health"] = round(decoded["health"], 1)
            elif type_index == PLAYER and len(item) > 7 and item[7]:
                slot["name"] = item[7]
    return out


def report(found):
    rows = sorted(found.items(), key=lambda kv: -sum(kv[1]["types"].values()))
    for v1, slot in rows:
        types = ", ".join(f"{t}x{n}" for t, n in sorted(slot["types"].items(), key=lambda kv: str(kv[0])))
        objects = {t: len(objs) for t, objs in slot["objects"].items()}
        pos = slot["pos"]
        track = f"{pos[0][:2]} -> {pos[-1][:2]} ({len(pos)} samples)" if pos else "-"
        print(f"V1={v1:5d} v2={sorted(slot['v2'])} name={slot['name']!r} health={slot['health']} "
              f"pos={track}\n        types: {types}  objects per type: {objects}")
    print("payload length per typeIndex (chunks, min..max):")
    for type_index, lengths in sorted(LENGTHS.items()):
        print(f"  {type_index:5d}  {len(lengths):6d}  {min(lengths)}..{max(lengths)}")


def check():
    # the 22-byte walking-test payload from alc-protocol-reference.md 2.4, behind its group mask
    alc = "01" + "f380008003" + "4b" + "1c" + "ffffff" + "52" + "460ab4d245436963280c" + "64"
    lines = [json.dumps({"type": "join_samples", "items": [
        [1, 7, 16, ALC, "0xa", len(alc) // 2, alc],
        [2, 7, 2, VITALS, "0xb", 6, "01" + "01" + "42c80000"],
        [3, 7, 2, PLAYER, "0xc", 1, "00", "Tester"],
        [4, 9, 2, ALC, "0xd", 3, "0100ff"],     # a trailing byte the field masks do not cover
    ]})]
    found = entities(lines)
    seven = found[7]
    assert seven["name"] == "Tester" and seven["health"] == 100.0, seven
    assert len(seven["pos"]) == 1 and abs(seven["pos"][0][0] - 8877.2) < 0.1, seven["pos"]
    assert found[9]["types"]["alc_inexact"] == 1, found[9]
    print("decode_join check ok")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        return check()
    report(entities(args.log.read_text(errors="ignore").splitlines()))


if __name__ == "__main__":
    main()
