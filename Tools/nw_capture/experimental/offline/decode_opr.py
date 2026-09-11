#!/usr/bin/env python3
"""Outpost Rush: the scoreboard stream and the game-mode map (score, outposts), read to the byte.

Varint: the prefix form with little-endian continuation. n leading one bits in the first byte mean n
more bytes; the first byte keeps its low 7-n bits as the lowest value bits, each following byte adds
8 bits above (1 byte < 0x80; `8c 16` = 0x0c | 0x16 << 6 = 1420; `c7 8f 05` = 7 | 0x8f << 5 | 0x05 << 13 = 45,543).
This is what made the scoreboard totals land on the end screen to the unit; the big-endian tail of
decode_alc_state.read_prefix_varint does not.

WarboardComponentClientFacet_OnUpdateWarboardStats (RMI 839), after the 16-byte facet uuid:
    u16 version | u8 local index | local row: mask varint + one varint per set bit
    | team block x2: u8 count, count x (u8 index, mask varint, values)
The stat bits (the initial full row of every player sets all nine):
    1 score, 2 damage, 7 deaths, 21 healing, 22 damage absorbed (third ranking column), 23 kills,
    26 assists, 27 npc kill assists, 38 unread (0 all match)
Values are running totals. Block order is the reverse of the manifest list order: the player's team
(first list in OnUpdateFullWarboardManifest) is block 1. Checked on the 2026-09-11 match: PetaWatt
1,320 / 87,390 / 12 / 8, async93 16,024 / 1,170,768 / 12 kills / 55, Bohemond healing 4,386 and
absorbed 22,340, all equal to the end screen.

GameModeReplicatedState (2343) deltas on the mode entity: `01 <member mask varint>`; the member at
mask 0x200 (`80 08`) is a map keyed by u32: `u8 count, u8, count x (key u32, 01, seq varint, value
varint)`. Keys: 4a6e9282 = team scores (value = score of the player's team | other team << 16, final
0x25103e9 = 1001 / 593), 448dd922 Luna, ca02dec1 Sol, 06a8de5f Astra (value bytes: owner team or ff,
capturing team or ff, capture progress). Outpost names by score attribution: the ticks credited to
each key while owned came out 339 / 459 / 199 for the player's team against 307 / 403 / 184 on the
end screen (kill points are spread in), same order on the other side.
"""
import argparse
import json
import struct
import sys
from pathlib import Path

STAT_BITS = {1: "score", 2: "damage", 7: "deaths", 21: "healing", 22: "absorbed", 23: "kills",
             26: "assists", 27: "npc_assists", 38: "stat38"}
OUTPOSTS = {"448dd922": "Luna", "ca02dec1": "Sol", "06a8de5f": "Astra"}
SCORE_KEY = "4a6e9282"


def read_varint(data: bytes, index: int):
    """Little-endian prefix varint; returns (value, next index)."""
    first = data[index]
    extra = 0
    while extra < 7 and first & (0x80 >> extra):
        extra += 1
    if index + 1 + extra > len(data):
        raise ValueError("varint past the end")
    low = 7 - extra
    value = first & ((1 << low) - 1)
    for k in range(extra):
        value |= data[index + 1 + k] << (low + 8 * k)
    return value, index + 1 + extra


def _row(data: bytes, index: int):
    mask, index = read_varint(data, index)
    values = {}
    bit = 0
    while mask >> bit:
        if mask >> bit & 1:
            values[bit], index = read_varint(data, index)
        bit += 1
    return values, index


def parse_warboard_stats(payload: bytes):
    """Return {"version", "local_index", "local", "teams": [[(index, {stat: total})...], ...]}."""
    data = payload[16:]
    version = struct.unpack(">H", data[:2])[0]
    local_index = data[2]
    local, index = _row(data, 3)
    teams = []
    while index < len(data):
        count = data[index]
        index += 1
        rows = []
        for _ in range(count):
            player = data[index]
            values, index = _row(data, index + 1)
            rows.append((player, {STAT_BITS.get(bit, f"bit{bit}"): v for bit, v in values.items()}))
        teams.append(rows)
    return {"version": version, "local_index": local_index,
            "local": {STAT_BITS.get(bit, f"bit{bit}"): v for bit, v in local.items()}, "teams": teams}


def parse_gamemode_map(payload: bytes):
    """The keyed map of a GameModeReplicatedState delta whose member mask is exactly 0x200 (`01 80 08`).
    Returns {key_hex: value} or {} for other shapes."""
    if payload[:3] != b"\x01\x80\x08" or len(payload) < 6:
        return {}
    count, index = payload[3], 5
    out = {}
    try:
        for _ in range(count):
            key = payload[index:index + 4].hex()
            index += 4
            if payload[index] != 1:
                return {}
            _seq, index = read_varint(payload, index + 1)
            out[key], index = read_varint(payload, index)
    except (ValueError, IndexError):
        return {}
    return out if index == len(payload) else {}


def find_map_entries(payload: bytes):
    """The same map entries inside any GameModeReplicatedState delta (other members set too): scan for
    the known keys followed by `01 <seq> <value>`. The final 1001 / 593 came in such a record (`01 81 01
    18 08 ff 4a6e9282 01 812e e93e1025`) two seconds after the last pure map delta (999 / 592)."""
    out = {}
    for key in (SCORE_KEY, *OUTPOSTS):
        raw = bytes.fromhex(key)
        start = payload.find(raw)
        while start >= 0:
            index = start + 4
            if index < len(payload) and payload[index] == 1:
                try:
                    _seq, index = read_varint(payload, index + 1)
                    value, index = read_varint(payload, index)
                    out[key] = value
                except (ValueError, IndexError):
                    pass
            start = payload.find(raw, start + 1)
    return out


def team_scores(value: int):
    return value & 0xFFFF, value >> 16


def outpost_state(value: int):
    owner, capturing, progress = value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF
    return {"owner": None if owner == 0xFF else owner, "capturing": None if capturing == 0xFF else capturing,
            "progress": progress}


def scoreboard(log_path: Path):
    """Final running totals per (block, index) from every 839 message of a log, plus the manifest."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from decode_rmi import parse_warboard_manifest_delta, player_uuid_name  # noqa: E402
    totals, names, lists, score, outposts = {}, {}, {}, None, {}
    for line in open(log_path):
        if '"join_samples"' in line:
            for item in json.loads(line)["items"]:
                if len(item) >= 7 and item[3] == 3935 and item[5] > 40:
                    who = player_uuid_name(bytes.fromhex(item[6]))
                    if who:
                        names[who[0]] = who[1]
                elif len(item) >= 7 and item[3] == 2343:
                    for key, value in find_map_entries(bytes.fromhex(item[6])).items():
                        if key == SCORE_KEY:
                            score = team_scores(value)
                        elif key in OUTPOSTS:
                            outposts[OUTPOSTS[key]] = outpost_state(value)
        elif '"rmi_samples"' in line:
            for item in json.loads(line)["items"]:
                if item[1] == 3530:
                    body = bytes.fromhex(item[2])
                    index, team = 18, 0
                    while index + 2 <= len(body):
                        count = struct.unpack(">H", body[index:index + 2])[0]
                        index += 2
                        uuids = [body[index + 1 + 17 * k:index + 17 + 17 * k].hex() for k in range(count)]
                        index += 17 * count
                        for uuid_hex, slot in zip(uuids, body[index:index + count]):
                            lists[(team, slot)] = uuid_hex
                        index += count + 2
                        team += 1
                elif item[1] == 2968:
                    for uuid_hex, (team, slot) in parse_warboard_manifest_delta(bytes.fromhex(item[2])).items():
                        lists[(team, slot)] = uuid_hex
                elif item[1] == 839:
                    try:
                        parsed = parse_warboard_stats(bytes.fromhex(item[2]))
                    except (ValueError, IndexError):
                        continue
                    for block, rows in enumerate(parsed["teams"]):
                        for player, values in rows:
                            totals.setdefault((block, player), {}).update(values)
    rows = []
    for (block, player), values in sorted(totals.items()):
        uuid_hex = lists.get((1 - block, player))
        rows.append({"block": block, "index": player, "name": names.get(uuid_hex, uuid_hex and uuid_hex[:8]), **values})
    return rows, score, outposts


def check():
    first = bytes.fromhex("cb094e95df9b24169d593e64310f6d6e" "000703000302fa210038031000000000000000000001fa210038031000000000000000000000fa2100380310000000000000000000"
                          "0402fa210038031000000000000000000001fa210038031000000000000000000003fa210038031000000000000000000000fa2100380310000000000000000000")
    parsed = parse_warboard_stats(first)
    assert parsed["local_index"] == 3 and parsed["local"] == {} and [len(t) for t in parsed["teams"]] == [3, 4], parsed
    assert parsed["teams"][0][0][1] == {name: 0 for name in STAT_BITS.values()}, parsed["teams"][0][0]
    # the player's ninth death: local row mask {1, 2, 7} = score 874, damage 84,944, deaths 9
    death = parse_warboard_stats(bytes.fromhex("cb094e95df9b24169d593e64310f6d6e" "0028038602aa0dd05e0a09030e06837ed5085f0d068477c12a680f02a5690313069c46c1353a1202a955038602aa0dd05e0a09"))
    assert death["local"] == {"score": 874, "damage": 84944, "deaths": 9}, death["local"]
    assert (3, {"score": 874, "damage": 84944, "deaths": 9}) in death["teams"][1], death["teams"][1]
    assert read_varint(bytes.fromhex("8c16"), 0)[0] == 1420 and read_varint(bytes.fromhex("c78f05"), 0)[0] == 45543
    # game mode map: final score 1001 / 593 and an outpost owned by team 1 with team 0 capturing at 3
    assert team_scores(read_varint(bytes.fromhex("e93e1025"), 0)[0]) == (1001, 593)
    game = parse_gamemode_map(bytes.fromhex("0180080101ca02dec101a504c10018"))
    assert outpost_state(game["ca02dec1"]) == {"owner": 1, "capturing": 0, "progress": 3}, game
    final = find_map_entries(bytes.fromhex("0181011808ff4a6e928201812ee93e1025428ad20201000089f106dc0100e313d008f59023070100e319b005689fc2710100"))
    assert team_scores(final[SCORE_KEY]) == (1001, 593), final
    print("decode_opr check ok")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--log", type=Path, help="a join-probe log with an Outpost Rush in it")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        check()
        return 0
    if not args.log:
        parser.error("--log or --check")
    rows, score, outposts = scoreboard(args.log)
    print(f"score {score}  outposts {outposts}")
    print(f"{'blk':>3} {'idx':>3} {'name':<18} {'score':>6} {'kills':>5} {'deaths':>6} {'assists':>7} {'damage':>9} {'healing':>9} {'absorbed':>8}")
    for row in sorted(rows, key=lambda r: (r['block'], -r.get('score', 0))):
        print(f"{row['block']:>3} {row['index']:>3} {str(row['name']):<18} {row.get('score', 0):>6} {row.get('kills', 0):>5} "
              f"{row.get('deaths', 0):>6} {row.get('assists', 0):>7} {row.get('damage', 0):>9} {row.get('healing', 0):>9} {row.get('absorbed', 0):>8}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
