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
from decode_alc_state import decode_record_payload, iter_records  # noqa: E402
from decode_vitals import parse_members  # noqa: E402

ALC, VITALS, PLAYER = 11, 15, 3935
LENGTHS = {}   # typeIndex -> payload lengths seen: the record-length oracle, exact per chunk


def log_items(lines):
    """The join_samples items of a probe log, in order."""
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get("type") == "join_samples":
            yield from entry.get("items", [])


def ledger_items(ledger_path):
    """The same item shape from a capture ledger, for the ALC records a body starts with.

    The ledger has no chunk lengths, so only the ALC records that decode exactly are yielded (the
    record walk stops at the first other type). Enough for the player's pose timeline: the player's
    ALC record (V1 = 1) is the first record of every body in the captures seen so far.
    """
    import bisect
    from decode_in_bodies import decode_record, iter_frames, iter_ledger, reassemble_channel_messages
    rows = []
    for index, dir_byte, ts_ms, ssl_ptr, payload in iter_ledger(Path(ledger_path)):
        datagram = decode_record(index, dir_byte, ts_ms, ssl_ptr, payload)
        if datagram.dir != "in":
            continue
        rows.extend((index, ts_ms, message) for message in datagram.messages if message.channel == 1)
    pieces, _ = reassemble_channel_messages(rows)
    offsets, stamps, stream = [], [], bytearray()
    for piece in pieces:
        offsets.append(len(stream))
        stamps.append(piece.get("ts_ms") or 0)
        stream += piece["payload"]
    for offset, _counter, body, _trailer in iter_frames(bytes(stream)):
        ts = stamps[max(0, bisect.bisect_right(offsets, offset) - 1)]
        for _start, v1, v2, _group_mask, payload_offset, _fields in iter_records(body):
            _fields, used = decode_record_payload(body, payload_offset)
            yield [ts, v1, v2, ALC, "", used, body[payload_offset:payload_offset + used].hex()]


def entities(items):
    """Return {v1: {"types": {typeIndex: count}, "objects": {typeIndex: set}, "pos", "health", "name"}}."""
    out = defaultdict(lambda: {"types": defaultdict(int), "objects": defaultdict(set), "pos": [],
                               "health": None, "name": None, "v2": set()})
    for item in items:
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


MOVING = ("idRel", "timeOffsetRel", "timeOffsetAbs", "worldPosAbs", "worldPosRel", "scopeTimeBlob0Data0",
          "slayerSeqTimeRel", "slayerSeqTimeAbs", "lookDir", "rotation", "idAbs")


def timeline(items, v1):
    """Print the ALC fields of one entity whenever the pose-related ones change.

    Fields that move every frame (ids, times, position, look) are left out, so what is printed is the
    slayer state machine: state id, sequence id, started stamp and the unnamed bits around them.
    """
    import datetime
    last = None
    for item in items:
        ts, item_v1, _v2, type_index, _obj, length, payload_hex = item[:7]
        if item_v1 != v1 or type_index != ALC:
            continue
        fields, used = decode_record_payload(bytes.fromhex(payload_hex), 0)
        if fields is None or used != length:
            continue
        pose = {name: value if value is not None else chunk.hex()
                for _bit, name, chunk, value in fields if name not in MOVING}
        if pose != last:
            stamp = datetime.datetime.fromtimestamp(ts / 1000).strftime("%H:%M:%S.%f")[:-3]
            print(stamp, pose)
            last = pose


def check():
    # the 22-byte walking-test payload from alc-protocol-reference.md 2.4, behind its group mask
    alc = "01" + "f380008003" + "4b" + "1c" + "ffffff" + "52" + "460ab4d245436963280c" + "64"
    lines = [json.dumps({"type": "join_samples", "items": [
        [1, 7, 16, ALC, "0xa", len(alc) // 2, alc],
        [2, 7, 2, VITALS, "0xb", 6, "01" + "01" + "42c80000"],
        [3, 7, 2, PLAYER, "0xc", 1, "00", "Tester"],
        [4, 9, 2, ALC, "0xd", 3, "0100ff"],     # a trailing byte the field masks do not cover
    ]})]
    found = entities(log_items(lines))
    seven = found[7]
    assert seven["name"] == "Tester" and seven["health"] == 100.0, seven
    assert len(seven["pos"]) == 1 and abs(seven["pos"][0][0] - 8877.2) < 0.1, seven["pos"]
    assert found[9]["types"]["alc_inexact"] == 1, found[9]
    print("decode_join check ok")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, help="nw_join_probe.js log")
    parser.add_argument("--ledger", type=Path, help="capture ledger.bin instead: ALC records only")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--timeline", type=int, metavar="V1",
                        help="print the pose fields of this entity when they change (1 = the player)")
    args = parser.parse_args(argv)
    if args.check:
        return check()
    if args.ledger:
        items = ledger_items(args.ledger)
    else:
        items = log_items(args.log.read_text(errors="ignore").splitlines())
    if args.timeline is not None:
        return timeline(items, args.timeline)
    report(entities(items))


if __name__ == "__main__":
    main()
