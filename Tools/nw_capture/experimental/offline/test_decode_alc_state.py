"""Checks for the ALC field decoder: wire vectors, then a known track from a real capture."""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))

from decode_alc_state import (  # noqa: E402
    GROUP0_READER_TABLE,
    GROUP1_READER_TABLE,
    decode_group_payload,
    decode_payload,
    decode_record_payload,
    read_mask_varint,
    read_prefix_varint,
    read_quaternion,
)

CAPTURE = HERE.parents[1] / "captures/proton_20260910_170210-pos2/dtls/ledger.bin"
# the walking test: this payload was decoded from the wire and matches what the position probe
# and the community map independently report for the same moment (east 8877.205, north 3126.587)
POSITION_PAYLOAD = bytes.fromhex("f3800080034b1cffffff52460ab4d245436963280c64")


class MaskVarintTest(unittest.TestCase):
    def test_sizes_and_values(self):
        self.assertEqual(read_mask_varint(bytes.fromhex("0a"), 0), (10, 1))
        self.assertEqual(read_mask_varint(bytes.fromhex("e3000040"), 0), (0x4000003, 4))
        self.assertEqual(read_mask_varint(bytes.fromhex("f380008003"), 0), (0x1C000403, 5))
        self.assertEqual(read_mask_varint(bytes.fromhex("fe031c00be7fff26"), 0),
                         (0x26ff7fbe001c03, 8))
        self.assertEqual(read_mask_varint(bytes.fromhex("ff0102030405060708"), 0),
                         (0x0807060504030201, 9))
        self.assertEqual(read_mask_varint(bytes.fromhex("f30000"), 0), (None, 0))

    def test_field_prefix_varint_is_distinct_from_mask_varint(self):
        self.assertEqual(read_prefix_varint(bytes.fromhex("911d"), 0), (1873, 2))
        self.assertEqual(read_prefix_varint(bytes.fromhex("c72004"), 0), (0x40087, 3))

    def test_bit_sets_match_the_observed_records(self):
        # e3 00 00 40: idRel, timeOffsetRel, timeOffsetAbs
        value, _ = read_mask_varint(bytes.fromhex("e3000040"), 0)
        self.assertEqual([b for b in range(63) if value >> b & 1], [0, 1, 26])
        # f3 80 00 80 03: idRel, timeOffsetRel, worldPosRel, timeOffsetAbs, worldPosAbs, blob0Data0
        value, _ = read_mask_varint(POSITION_PAYLOAD, 0)
        self.assertEqual([b for b in range(63) if value >> b & 1], [0, 1, 10, 26, 27, 28])


class GroupReaderMapTest(unittest.TestCase):
    def test_runtime_group0_reader_map_and_widths(self):
        self.assertEqual(GROUP0_READER_TABLE[8], ("group0.bit8", "halfFloat"))
        self.assertEqual(GROUP0_READER_TABLE[9], ("group0.bit9", "halfFloat"))
        self.assertEqual(GROUP0_READER_TABLE[27], ("worldPosAbs", "worldPosAbs"))
        self.assertEqual(GROUP0_READER_TABLE[33], ("scopeInfoBlob", "bytes177"))
        self.assertEqual(GROUP0_READER_TABLE[36], ("group0.bit36", "halfFloat"))
        self.assertEqual(GROUP0_READER_TABLE[40], ("group0.bit40", "u64"))
        self.assertEqual(GROUP0_READER_TABLE[48], ("group0.bit48", "prefixVarint"))

    def test_group1_only_has_the_observed_bit_zero_reader(self):
        self.assertEqual(GROUP1_READER_TABLE, {0: ("group1.bit0", "u8State")})


class GroupPayloadTest(unittest.TestCase):
    def test_group0_payload_uses_runtime_readers_and_consumes_exactly(self):
        payload = bytes.fromhex(
            "fb0003008510"
            "5198"
            "8dec83"
            "66c9"
            "54"
            "0a"
            "0708510c17000037"
            "00"
        )
        fields, used = decode_group_payload(payload)
        self.assertEqual(used, len(payload))
        self.assertEqual([bit for bit, _, _, _ in fields],
                         [0, 1, 10, 11, 26, 28, 33, 38])
        self.assertEqual([len(chunk) for _, _, chunk, _ in fields],
                         [1, 1, 3, 2, 1, 1, 8, 1])

    def test_record_payload_reads_group_mask_and_both_groups(self):
        fields, used = decode_record_payload(bytes.fromhex("0301aa01bb"))
        self.assertEqual(used, 5)
        self.assertEqual([(bit, name, chunk) for bit, name, chunk, _ in fields],
                         [(0, "idRel", b"\xaa"), (0, "group1.bit0", b"\xbb")])

class QuaternionTest(unittest.TestCase):
    def test_component_counts(self):
        for control, size in ((0x11, 3), (0x3A, 1), (0x66, 2), (0x83, 3)):
            self.assertEqual(read_quaternion(bytes([control]) + b"\x00" * 4, 0)[1], size,
                             f"control {control:#x}")


class PayloadTest(unittest.TestCase):
    def test_position_payload_is_consumed_exactly(self):
        fields, used = decode_payload(POSITION_PAYLOAD)
        self.assertEqual(used, len(POSITION_PAYLOAD))
        by_name = {name: value for _, name, _, value in fields}
        self.assertEqual(by_name["worldPosRel"], "no update")
        self.assertEqual(by_name["worldPosAbs"],
                         {"east": 8877.205, "north": 3126.587, "elevation": 72.079})


class CaptureTest(unittest.TestCase):
    @unittest.skipUnless(CAPTURE.exists(), "capture is gitignored and not present")
    def test_record_boundaries_and_known_positions(self):
        from decode_alc_state import iter_records
        from decode_in_bodies import channel_stream, iter_frames

        wanted = {bytes.fromhex("460ab4d245436963280c")}
        found = set()
        group_masks = set()
        records = 0
        for _offset, _counter, body, _trailer in iter_frames(channel_stream(str(CAPTURE))):
            for _start, _v1, _v2, group_mask, _payload_offset, fields in iter_records(body):
                records += 1
                group_masks.add(group_mask)
                for _bit, name, chunk, _value in fields:
                    if name == "worldPosAbs":
                        found.add(chunk)
        self.assertGreater(records, 100)
        self.assertEqual(group_masks, {1, 3})
        self.assertTrue(wanted <= found, "the known walking-test position is not on the wire")


if __name__ == "__main__":
    unittest.main()
