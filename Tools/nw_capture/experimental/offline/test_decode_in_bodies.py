#!/usr/bin/env python3
"""Checks for the inbound body decoder and the wire id resolver.

Run with the repository convention:

    .venv-capture/bin/python -m unittest discover -s Tools/nw_capture -p 'test_*.py'
"""
from __future__ import annotations

import json
import struct
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
_CAPTURE_TOOL = _HERE.parents[1]
if str(_CAPTURE_TOOL) not in sys.path:
    sys.path.insert(0, str(_CAPTURE_TOOL))

import decode_in_bodies as bodies  # noqa: E402
import decode_wire_type_ids as wire  # noqa: E402

LEDGER = _CAPTURE_TOOL / "captures" / "offline-position-scratch" / "ledger.bin"


def encode_prefix_varint(value):
    """Inverse of read_prefix_varint, written from the verified decoder."""
    if value < 0x80:
        return bytes([value])
    if value < 0x4000:
        return bytes([0x80 | (value & 0x3F), (value >> 6) & 0xFF])
    if value < 0x200000:
        tail = value >> 5
        return bytes([0xC0 | (value & 0x1F), (tail >> 8) & 0xFF, tail & 0xFF])
    if value < 0x10000000:
        tail = value >> 4
        return bytes([0xE0 | (value & 0x0F), (tail >> 16) & 0xFF,
                      (tail >> 8) & 0xFF, tail & 0xFF])
    tail = value >> 3
    return bytes([0xF0 | (value & 0x07), (tail >> 24) & 0xFF, (tail >> 16) & 0xFF,
                  (tail >> 8) & 0xFF, tail & 0xFF])


class PrefixVarintTests(unittest.TestCase):
    """The decoder must match the encoding implemented in the binary (FUN_140877970/14087b5c0)."""

    def test_known_widths(self):
        self.assertEqual(bodies.read_prefix_varint(bytes([0x07]), 0), (7, 1))
        self.assertEqual(bodies.read_prefix_varint(bytes([0xBF, 0x01]), 0), (127, 2))
        self.assertEqual(bodies.read_prefix_varint(bytes([0x86, 0x10]), 0), (1030, 2))

    def test_round_trip(self):
        for value in (0, 1, 7, 126, 127, 128, 1031, 16383, 16384, 2000000,
                      0x0FFFFFFF - 1, 0x0FFFFFFF):
            encoded = encode_prefix_varint(value)
            decoded, size = bodies.read_prefix_varint(encoded, 0)
            self.assertEqual(decoded, value, f"value {value} encoded {encoded.hex()}")
            self.assertEqual(size, len(encoded))

    def test_truncated_is_rejected(self):
        self.assertEqual(bodies.read_prefix_varint(bytes([0xF0, 0x01]), 0), (None, 0))
        self.assertEqual(bodies.read_prefix_varint(b"", 0), (None, 0))


class FrameTests(unittest.TestCase):
    """The frame is marker + u32 counter + 4 bytes + u16 BE length + body + prefix varint."""

    @staticmethod
    def build_frame(counter, body, trailer_value=17):
        head = bodies.MARKER + struct.pack("<I", counter) + bytes.fromhex("04010100")
        head += struct.pack(">H", len(body))
        return head + body + encode_prefix_varint(trailer_value)

    def test_frame_round_trip(self):
        body = bytes.fromhex("01100b01") + b"\x2b\x87"
        stream = self.build_frame(1000, body) + self.build_frame(1001, body)
        frames = list(bodies.iter_frames(stream))
        self.assertEqual(len(frames), 1, "only the first frame has a following marker to close on")
        offset, counter, parsed_body, trailer = frames[0]
        self.assertEqual(counter, 1000)
        self.assertEqual(parsed_body, body)
        self.assertEqual(trailer, 1)

    def test_open_frame_is_not_reported(self):
        stream = self.build_frame(5, b"\x01\x02\x03")
        self.assertEqual(list(bodies.iter_frames(stream)), [])


class RecordTests(unittest.TestCase):
    """A body is a leading byte plus records of tag + varint + payload."""

    def test_split_records(self):
        tag = bodies.RECORD_TAG
        body = b"\x01" + tag + bytes([0x07]) + b"\xcd\xf0\xdf\x3b" + tag + bytes([0x86, 0x10]) + b"\x01\x02"
        leading, records, leftover = bodies.split_records(body)
        self.assertEqual(leading, b"\x01")
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0][1], 7)
        self.assertEqual(records[0][2], b"\xcd\xf0\xdf\x3b")
        self.assertEqual(records[1][1], 1030)
        self.assertEqual(records[1][2], b"\x01\x02")
        self.assertEqual(leftover, b"")

    def test_body_without_tag(self):
        leading, records, leftover = bodies.split_records(b"\xaa\xbb\xcc")
        self.assertEqual(records, [])
        self.assertEqual(leading, b"\xaa\xbb\xcc")


class WireIdTests(unittest.TestCase):
    """Observed ids must resolve against the registry's typeIndex space."""

    REGISTRY = {
        "entries": [
            {"typeIndex": 11, "index": 1075, "uuid": "01B0664B-3AB6-44A6-87E3-8C69D40E0365",
             "name": "", "communityName": ""},
            {"typeIndex": 349, "index": 74, "uuid": "6A379FB8-0BDD-43A1-AB3E-9843D7BE8CD3",
             "name": "PingMsg", "communityName": "PingMsg"},
        ]
    }

    def test_resolve_without_binary(self):
        import collections
        rows = wire.resolve(collections.Counter({11: 5, 349: 2, 999999: 1}), self.REGISTRY, None)
        by_id = {row["typeIndex"]: row for row in rows}
        self.assertTrue(by_id[11]["in_registry"])
        self.assertEqual(by_id[11]["registryIndex"], 1075)
        self.assertEqual(by_id[349]["name"], "PingMsg")
        self.assertFalse(by_id[999999]["in_registry"])

    def test_observed_trace_id_extraction(self):
        """The extraction reads uuid_refs payloads only."""
        import tempfile
        payload = {
            "type": "uuid_refs",
            "items": [[1, "idx", 11, "", ""], [1, "raw16", 0, "0x1", "00" * 16],
                      [2, "idx", 11, "", ""]],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False) as handle:
            handle.write(json.dumps(payload) + "\n")
            handle.write('{"type":"other","items":[]}\n')
            path = Path(handle.name)
        try:
            counts = wire.observed_ids_from_trace(path)
        finally:
            path.unlink()
        self.assertEqual(dict(counts), {11: 2})


class RealCaptureTests(unittest.TestCase):
    """Regression guard on the committed-by-hand teleport ledger fixture."""

    def setUp(self):
        if not LEDGER.exists():
            self.skipTest(f"fixture not present: {LEDGER}")

    def test_frames_and_records(self):
        result = bodies.analyze(LEDGER, limit=600)
        self.assertGreater(result["frames"], 200)
        self.assertGreater(result["records_total"], 200)
        self.assertGreater(result["bodies_with_records"], 200)
        # the record hypothesis must not silently explain only a handful of bodies
        share = result["bodies_with_records"] / result["frames"]
        self.assertGreater(share, 0.90)


if __name__ == "__main__":
    unittest.main(verbosity=2)
