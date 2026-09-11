"""What an ALC record says about how an entity looks: pose label and heading.

Pose: slayer state ids of layers 0 (locomotion) and 1 (weapon); names come from driven keys and
mouse actions (docs/Network/pose-state.md), an id not in the table is reported as its number.

Heading: the ``rotation`` quaternion, FUN_14087a8d0 (smallest-three): control byte c, bits 5-6 the
index of the largest component (reconstructed), bits 1-4 "component x/y/z/w is zero", bit 0 the
sign of the largest; each transmitted byte is ``b * sqrt(2)/255 - sqrt(2)/2``. The body yaw about Z
with forward = +Y: on two driven walks the movement heading was yaw + 90 degrees (east = 0, north =
90), so that is what ``heading_deg`` returns.
"""
import math
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


QUANT = math.sqrt(2) / 255
HALF_SQRT2 = math.sqrt(2) / 2


def quaternion(chunk: bytes):
    """Decode the compressed quaternion [x, y, z, w], or None if the byte count does not fit."""
    control = chunk[0]
    largest = control >> 5 & 3
    q = [0.0] * 4
    index, total = 1, 0.0
    for k in range(4):
        if k == largest or control >> (k + 1) & 1:
            continue
        if index >= len(chunk):
            return None
        q[k] = chunk[index] * QUANT - HALF_SQRT2
        total += q[k] * q[k]
        index += 1
    if index != len(chunk):
        return None
    q[largest] = math.sqrt(max(0.0, 1.0 - total)) * (-1.0 if control & 1 else 1.0)
    return q


def heading_deg(q) -> float:
    """Map heading in degrees, east = 0, north = 90, from a body-yaw quaternion (forward = +Y)."""
    x, y, z, w = q
    yaw = math.degrees(math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z)))
    return (yaw + 90.0 + 180.0) % 360.0 - 180.0


def pose_from_payload(payload: bytes):
    """Return {"pose": {layer: {"id", "name"}}, "heading": deg} for what this record carries."""
    fields, used = decode_record_payload(payload, 0)
    if fields is None or used != len(payload):
        return {}
    out = {}
    for bit, name, chunk, _value in fields:
        layer = STATE_ID_BITS.get(bit)
        if name == "rotation":
            q = quaternion(chunk)
            if q is not None:
                out["heading"] = round(heading_deg(q), 1)
        elif layer is not None and name == "slayerStateId":
            state_id, size = read_prefix_varint(chunk, 0)
            if size == len(chunk):
                out.setdefault("pose", {})[layer] = {
                    "id": state_id, "name": LAYER_NAMES.get(layer, {}).get(state_id, str(state_id))}
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
    assert pose_from_payload(payload) == {"pose": {0: {"id": 0x1a, "name": "walking"}}}, pose_from_payload(payload)
    mask = encode_mask_varint((1 << 0) | (1 << 1) | (1 << 16))
    payload = bytes([0x01]) + mask + bytes([0x4b, 0x1c, 0x2d])
    assert pose_from_payload(payload) == {"pose": {1: {"id": 0x2d, "name": "weapon out"}}}, pose_from_payload(payload)
    payload = bytes([0x01]) + mask + bytes([0x4b, 0x1c, 0x77])
    assert pose_from_payload(payload) == {"pose": {1: {"id": 0x77, "name": "119"}}}
    # rotation 46 96 from the joinwalk (11:25:22): z largest, x and y zero, w = 150 -> yaw 165.7, heading -104.3;
    # the walk itself moved at -109.4, five degrees off while the body was still turning
    q = quaternion(bytes.fromhex("4696"))
    assert [round(v, 2) for v in q] == [0.0, 0.0, 0.99, 0.12], q
    assert abs(heading_deg(q) - (-104.3)) < 0.1, heading_deg(q)
    assert quaternion(bytes.fromhex("46")) is None and quaternion(bytes.fromhex("469600")) is None
    mask = encode_mask_varint((1 << 0) | (1 << 1) | (1 << 11))
    assert pose_from_payload(bytes([0x01]) + mask + bytes([0x4b, 0x1c, 0x46, 0x96])) == {"heading": -104.3}
    print("decode_pose check ok")


if __name__ == "__main__":
    check()
