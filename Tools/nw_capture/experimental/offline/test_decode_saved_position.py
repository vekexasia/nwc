#!/usr/bin/env python3
"""Small offline self-check for the saved-position diagnostic."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import struct
import tempfile


SCRIPT = Path(__file__).with_name("decode_saved_position.py")
spec = importlib.util.spec_from_file_location("decode_saved_position", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FakeMessage:
    def __init__(self, payload, num_chunks=None, seq=1, rel_seq=1):
        self.payload = payload
        self.num_chunks = num_chunks
        self.seq = seq
        self.rel_seq = rel_seq
        self.flags = 0x25 if num_chunks is not None else 0x21


def main():
    rows = [
        (10, 1000, FakeMessage(b"A", 3, seq=1)),
        (11, 1001, FakeMessage(b"B", 2, seq=2)),
        (12, 1002, FakeMessage(b"C", seq=3)),
        (13, 1003, FakeMessage(b"D", seq=4)),
    ]
    complete, errors = module.reassemble_channel_messages(rows)
    assert not errors
    assert [item["payload"] for item in complete] == [b"ABC", b"D"]
    assert [item["parts"] for item in complete] == [3, 1]


    broken, errors = module.reassemble_channel_messages([
        (20, 2000, FakeMessage(b"A", 4, seq=10)),
        (21, 2001, FakeMessage(b"B", 2, seq=11)),
        (22, 2002, FakeMessage(b"C", seq=12)),
    ])
    assert errors["chunk_countdown_break"] == 1
    assert [item["payload"] for item in broken] == [b"C"]

    incomplete, errors = module.reassemble_channel_messages([
        (30, 3000, FakeMessage(b"A", 3, seq=10)),
        (31, 3001, FakeMessage(b"B", 2, seq=11)),
    ])
    assert errors["unterminated_chunk_group"] == 1
    assert not incomplete

    gap, errors = module.reassemble_channel_messages([
        (40, 4000, FakeMessage(b"A", 3, seq=10)),
        (41, 4001, FakeMessage(b"B", 2, seq=12)),
        (42, 4002, FakeMessage(b"C", seq=13)),
    ])
    assert errors["chunk_sequence_break"] == 1
    assert [item["payload"] for item in gap] == [b"C"]
    carrier, trailer = module.parse_carrier_messages(
        b"\x30\x00\x01\x01\x00\x07A\x38\x00\x01\x01B")
    assert not trailer
    assert [message.seq for message in carrier] == [7, 8]
    assert [message.payload for message in carrier] == [b"A", b"B"]
    reliable, trailer = module.parse_carrier_messages(
        b"\x21\x00\x01\x01\xff\xff\x00\x2aA\x39\x00\x01\x01B")
    assert not trailer
    assert [message.seq for message in reliable] == [65535, 0]
    assert [message.rel_seq for message in reliable] == [42, 43]
    assert [message.payload for message in reliable] == [b"A", b"B"]
    truncated = b"\x20\x00\x00"
    assert module.parse_carrier_messages(truncated) == ([], truncated)
    unknown = b"\x40\x00\x00"
    assert module.parse_carrier_messages(unknown) == ([], unknown)
    datagram = module.decode_record(0, 0, 0, 0, b"\x80\x01\x00\x00" + truncated)
    assert datagram.error is None
    assert datagram.carrier_error == "truncated carrier channel"
    assert datagram.trailer == truncated
    messages, framing, trailing = module.parse_inbound_application_stream([
        {"payload": b"\x03ab"}, {"payload": b"c\x00"}])
    assert [item["payload"] for item in messages] == [b"abc", b""]
    assert not framing and trailing == 0
    messages, framing, trailing = module.parse_inbound_application_stream([
        {"payload": b"\x05ab"}])
    assert not messages and framing["inbound_message_truncated"] == 1
    assert trailing == 3
    marker_like = b"xx\x00\x01\x08\x01\xff"
    stats, positions, body, rejected = module.analyze_application([
        {"payload": marker_like},
    ])
    assert stats["marker_like_occurrences"] == 1
    assert positions == {2: 1}
    assert body["invalid_has_sequence"] == 1

    candidate = b"\x00\x01\x08\x01" + bytes((0, 1, 2, 0, 0, 0))
    outcome, consumed = module.parse_state_bundle_hypothesis(candidate, 4)
    assert outcome == "accepted"
    assert consumed == len(candidate)
    stats, positions, body, rejected = module.analyze_application([
        {"payload": candidate},
    ])
    assert stats["state_bundle_hypothesis_exact_consumption"] == 1
    assert rejected["accepted"] == 1
    assert positions == {0: 1}
    assert body["valid_has_sequence"] == 1
    optional = (b"\x00\x01\x08\x01"
                + bytes((0, 1, 2, 0, 1, 1, 1, 0, 2, 0)))
    outcome, consumed = module.parse_state_bundle_hypothesis(optional, 4)
    assert outcome == "accepted"
    assert consumed == len(optional)


    frame = b"\x30\x00\x00\x01\x00\x01"
    payload = b"\x80\x01\x00\x00" + frame
    with tempfile.TemporaryDirectory() as directory:
        reused_path = Path(directory) / "reused.bin"
        with reused_path.open("wb") as handle:
            for index, pointer in enumerate((1, 2, 1)):
                handle.write(struct.pack("<IQBBBBQI", module.LEDGER_MAGIC,
                                         index, 0, 0, 0, 0, pointer,
                                         len(payload)))
                handle.write(payload)
        reused = module.run(reused_path)
        assert reused["status"] == "ok"
        assert [item["label"] for item in reused["connections"]] == [
            "conn-01", "conn-02", "conn-03"]
    with tempfile.TemporaryDirectory() as directory:
        incomplete_path = Path(directory) / "ledger.bin"
        incomplete_path.write_bytes(b"x")
        incomplete = module.run(incomplete_path)
        assert incomplete["status"] == "invalid_ledger_incomplete"
        assert incomplete["datagrams"] == 0
    print("OK - offline reassembly and rejection checks")


if __name__ == "__main__":
    main()
