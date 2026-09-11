"""The pose label of an ALC record: slayer state ids of layers 0 (locomotion) and 1 (weapon).

Names come from driven keys and mouse actions (docs/Network/pose-state.md); an id not in the table
is reported as its number, never guessed.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from decode_alc_state import decode_record_payload, read_prefix_varint  # noqa: E402

LAYER_NAMES = {
    0: {0x1f: "idle", 0x1a: "walking", 0x0d: "running", 0x0b: "dodge", 0x07: "sprint",
        0x0c: "sprint", 0x1b: "stopping", 0x0e: "jump"},
    1: {0x2c: "drawing weapon", 0x2d: "weapon out", 0x21: "light attack", 0x27: "heavy attack",
        0x24: "ability"},
}
# reader-vector bits 13..24 are the four (stateId, stateIdStarted, sequenceId) triplets
STATE_ID_BITS = {13: 0, 16: 1, 19: 2, 22: 3}


def pose_from_payload(payload: bytes):
    """Return {layer: {"id": int, "name": str}} for the layers whose state id is in this record."""
    fields, used = decode_record_payload(payload, 0)
    if fields is None or used != len(payload):
        return {}
    out = {}
    for bit, name, chunk, _value in fields:
        layer = STATE_ID_BITS.get(bit)
        if layer is None or name != "slayerStateId":
            continue
        state_id, size = read_prefix_varint(chunk, 0)
        if size != len(chunk):
            continue
        out[layer] = {"id": state_id, "name": LAYER_NAMES.get(layer, {}).get(state_id, str(state_id))}
    return out


def check():
    # poseA 11:47:16.161: layer 0 sequence change plus layer 1 weapon draw, from the join log
    walk = bytes.fromhex("01" + "f380008003" + "4b" + "1c" + "ffffff" + "52" + "460ab4d245436963280c" + "64")
    assert pose_from_payload(walk) == {}, "no state id in the reference walk payload"
    # a payload built from the reference: bits 0, 1, 13 (layer 0 state 0x1a) -> mask e3 00 00 40 is bits 0,1,26,
    # so use the mask f3 00 20 00 = bits 0, 1, 13 (payload bits: 0x2000 -> byte 2 of the LE extra = 0x20)
    from encode_alc_state import encode_mask_varint
    mask = encode_mask_varint((1 << 0) | (1 << 1) | (1 << 13))
    payload = bytes([0x01]) + mask + bytes([0x4b, 0x1c, 0x1a])
    assert pose_from_payload(payload) == {0: {"id": 0x1a, "name": "walking"}}, pose_from_payload(payload)
    mask = encode_mask_varint((1 << 0) | (1 << 1) | (1 << 16))
    payload = bytes([0x01]) + mask + bytes([0x4b, 0x1c, 0x2d])
    assert pose_from_payload(payload) == {1: {"id": 0x2d, "name": "weapon out"}}, pose_from_payload(payload)
    payload = bytes([0x01]) + mask + bytes([0x4b, 0x1c, 0x77])
    assert pose_from_payload(payload) == {1: {"id": 0x77, "name": "119"}}
    print("decode_pose check ok")


if __name__ == "__main__":
    check()
