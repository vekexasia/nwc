#!/usr/bin/env python3
"""Encode and verify the Carrier datagram layer above the DTLS ledger.

The encoder follows ``decode_dtls_ledger.py`` exactly.  The ``mode_byte`` is
the first datagram byte at parser lines 203-205, accepted by the IDA-verified
``NW_Carrier_ReceiveDataPackets`` check at ``0x145DDE366`` and parser lines
218-224.  The ``format_byte`` is the second byte at lines 203-205, checked by
``NW_Carrier_SendDataPackets`` at ``0x145DDF483`` and parser lines 214-217; the
big-endian u16 ``dgram_seq`` is at lines 203-205.  The
Carrier stream then writes, in parser order (lines 131-181): flags (the
Carrier.h:76-82 bits at lines 35-41), big-endian u16 data_size, optional u8
channel, optional big-endian u16 num_chunks, sequence u16 (lines 152-164),
reliable sequence u16 (lines 165-175), payload bytes, and the retained trailer
(lines 120-121 and 176-183).

The verified parser uses the full post-header body at lines 223-232 as the
raw LZ4 block when mode bit 0 is set; the apparent compressor header is not
removed by its implementation.  A parsed Datagram does not retain the raw
compressed bytes, so an exact compressed block cannot be selected safely by
encode_datagram.  Compressed inputs therefore use the receiver-compatible
uncompressed mode on output.  The check separately measures whether
lz4.block.compress(..., store_size=False) happens to reproduce each original
block.
"""
from collections import Counter
from pathlib import Path
import struct
import sys

import lz4.block

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
if str(HERE.parent.parent) not in sys.path:
    sys.path.insert(0, str(HERE.parent.parent))

from decode_dtls_ledger import (  # noqa: E402
    CarrierMessage,
    Datagram,
    MF_CHUNKS,
    MF_CONNECTING,
    MF_DATA_CHANNEL,
    MF_RELIABLE,
    MF_SQUENTIAL_ID,
    MF_SQUENTIAL_REL_ID,
    decode_record,
    iter_ledger,
)

KNOWN_FLAGS = (MF_RELIABLE | MF_CHUNKS | MF_SQUENTIAL_ID |
               MF_SQUENTIAL_REL_ID | MF_DATA_CHANNEL | MF_CONNECTING)
MAX_U8 = 0xFF
MAX_U16 = 0xFFFF
CAPTURES = (
    ROOT / "Tools/nw_capture/captures/proton_20260910_174014-alcact/dtls/ledger.bin",
    ROOT / "Tools/nw_capture/captures/proton_20260911_112222-join3/dtls/ledger.bin",
)
LZ4_SIZE_HINTS = (256, 1024, 4096, 16384, 65536, 262144)


def _integer(value, name, maximum):
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer")
    if value < 0 or value > maximum:
        raise ValueError(f"{name} must be between 0 and {maximum}")
    return value


def _bytes(value, name):
    if not isinstance(value, (bytes, bytearray, memoryview)):
        raise TypeError(f"{name} must be bytes-like")
    return bytes(value)


def _required_integer(value, name, maximum):
    if value is None:
        raise ValueError(f"{name} is required by the Carrier flags")
    return _integer(value, name, maximum)


def _encode_message(message, is_first, previous_seq, previous_rel_seq):
    """Encode one CarrierMessage and return it with the new sequence values."""
    assert isinstance(message, CarrierMessage)
    flags = _integer(message.flags, "flags", MAX_U8)
    if flags & ~KNOWN_FLAGS:
        raise ValueError(f"unknown carrier flags 0x{flags & ~KNOWN_FLAGS:02x}")
    data_size = _integer(message.data_size, "data_size", MAX_U16)
    payload = _bytes(message.payload, "payload")
    if data_size != len(payload):
        raise ValueError(
            f"data_size {data_size} does not match payload length {len(payload)}"
        )

    output = bytearray(struct.pack(">BH", flags, data_size))
    if flags & MF_DATA_CHANNEL:
        channel = _required_integer(message.channel, "channel", MAX_U8)
        output.append(channel)
    elif message.channel is not None:
        raise ValueError("channel is present without MF_DATA_CHANNEL")

    if flags & MF_CHUNKS:
        num_chunks = _required_integer(message.num_chunks, "num_chunks", MAX_U16)
        output.extend(struct.pack(">H", num_chunks))
    elif message.num_chunks is not None:
        raise ValueError("num_chunks is present without MF_CHUNKS")

    # Parser lines 152-164: the first message, or a message without
    # MF_SQUENTIAL_ID, carries a big-endian sequence u16; later flagged
    # messages carry no field and derive previous_seq + 1.
    if is_first or not (flags & MF_SQUENTIAL_ID):
        seq = _required_integer(message.seq, "seq", MAX_U16)
        output.extend(struct.pack(">H", seq))
    else:
        if previous_seq is None:
            raise ValueError("missing Carrier sequence baseline")
        seq = (previous_seq + 1) & MAX_U16
        if message.seq != seq:
            raise ValueError(f"derived seq {seq} does not match message seq {message.seq}")

    # Parser lines 165-175: rel_seq is explicit until a baseline exists, then
    # MF_SQUENTIAL_REL_ID omits the field and derives previous_rel_seq + 1.
    if not (flags & MF_SQUENTIAL_REL_ID) or previous_rel_seq is None:
        rel_seq = _required_integer(message.rel_seq, "rel_seq", MAX_U16)
        output.extend(struct.pack(">H", rel_seq))
    else:
        rel_seq = (previous_rel_seq + 1) & MAX_U16
        if message.rel_seq != rel_seq:
            raise ValueError(
                f"derived rel_seq {rel_seq} does not match message rel_seq {message.rel_seq}"
            )

    # Parser lines 176-181 consume exactly data_size payload bytes.
    output.extend(payload)
    return bytes(output), seq, rel_seq


def encode_message_stream(datagram):
    """Encode the Carrier messages and the parser-retained trailer."""
    assert isinstance(datagram, Datagram)
    output = bytearray()
    previous_seq = None
    previous_rel_seq = None
    for index, message in enumerate(datagram.messages):
        encoded, previous_seq, previous_rel_seq = _encode_message(
            message, index == 0, previous_seq, previous_rel_seq
        )
        output.extend(encoded)
    output.extend(_bytes(datagram.trailer, "trailer"))
    return bytes(output)


def encode_datagram(datagram):
    """Rebuild one parsed Carrier datagram, using uncompressed output for LZ4."""
    assert isinstance(datagram, Datagram)
    if datagram.error is not None:
        raise ValueError(f"cannot encode invalid datagram: {datagram.error}")
    if datagram.additional_header is not None:
        raise ValueError(
            "cannot encode additional_header: the parser retains no raw header bytes"
        )

    mode_byte = _integer(datagram.mode_byte, "mode_byte", MAX_U8)
    format_byte = _integer(datagram.format_byte, "format_byte", MAX_U8)
    dgram_seq = _integer(datagram.dgram_seq, "dgram_seq", MAX_U16)
    if mode_byte not in (0x80, 0x81):
        raise ValueError(f"unexpected mode byte 0x{mode_byte:02x}")
    if format_byte != 0x01:
        raise ValueError(f"unexpected format byte 0x{format_byte:02x}")
    if type(datagram.compressed) is not bool:
        raise TypeError("compressed must be a bool")
    if datagram.compressed != bool(mode_byte & 0x01):
        raise ValueError("compressed does not match the datagram mode byte")

    stream = encode_message_stream(datagram)
    if datagram.decompressed_len is not None:
        decompressed_len = _integer(
            datagram.decompressed_len, "decompressed_len", (1 << 31) - 1
        )
        if decompressed_len != len(stream):
            raise ValueError(
                f"decompressed_len {decompressed_len} does not match stream length {len(stream)}"
            )

    # The parsed object has no original compressed body to compare with.  A
    # guessed LZ4 block could differ while retaining the same message bytes,
    # so mode 0x80 is the only exact, receiver-compatible fallback.
    output_mode = 0x80 if datagram.compressed else mode_byte
    return bytes((output_mode, format_byte)) + struct.pack(">H", dgram_seq) + stream


def compress_message_stream(stream):
    """Return the raw LZ4 block form used by the parser's compressed branch."""
    return lz4.block.compress(_bytes(stream, "stream"), store_size=False)


def _decompress_body(payload, datagram):
    """Decompress a valid body using the parser's bounded size-hint sequence."""
    body = payload[4:]
    decoded = None
    for size_hint in LZ4_SIZE_HINTS:
        try:
            decoded = lz4.block.decompress(body, uncompressed_size=size_hint)
            break
        except lz4.block.LZ4BlockError:
            continue
    assert decoded is not None
    if datagram.decompressed_len is not None:
        assert len(decoded) == datagram.decompressed_len
    return decoded


def _difference(original, encoded, offset_base=0):
    limit = min(len(original), len(encoded))
    index = next((i for i in range(limit) if original[i] != encoded[i]), limit)
    if index == limit and len(original) == len(encoded):
        return None
    start = max(0, index - 8)
    end = min(max(len(original), len(encoded)), index + 16)
    return (
        f"offset={offset_base + index} "
        f"original[{start}:{min(end, len(original))}]={original[start:end].hex()} "
        f"encoded[{start}:{min(end, len(encoded))}]={encoded[start:end].hex()}"
    )


def _new_report(path):
    return {
        "ledger": path,
        "datagrams_tested": 0,
        "datagrams_identical": 0,
        "datagrams_different": 0,
        "message_streams_identical": 0,
        "compressed_datagrams": 0,
        "compressed_streams_identical": 0,
        "lz4_canonical_identical": 0,
        "lz4_canonical_different": 0,
        "lz4_original_bytes": 0,
        "lz4_canonical_bytes": 0,
        "difference_classes": Counter(),
        "first_differences": {},
    }


def analyze_ledger(path):
    report = _new_report(path)
    for idx, dir_byte, ts_ms, ssl_ptr, payload in iter_ledger(path):
        datagram = decode_record(idx, dir_byte, ts_ms, ssl_ptr, payload)
        assert datagram.error is None, (path, idx, datagram.error)
        assert len(payload) >= 4
        report["datagrams_tested"] += 1
        original_stream = (
            _decompress_body(payload, datagram)
            if datagram.compressed
            else payload[4:]
        )
        encoded = encode_datagram(datagram)
        if encoded == payload:
            report["datagrams_identical"] += 1
        else:
            report["datagrams_different"] += 1
            failure_class = (
                "compressed mode fallback"
                if datagram.compressed
                else "uncompressed Carrier re-encode"
            )
            report["difference_classes"][failure_class] += 1
            if failure_class not in report["first_differences"]:
                report["first_differences"][failure_class] = _difference(
                    payload, encoded
                )

        if encoded[4:] == original_stream:
            report["message_streams_identical"] += 1
        if datagram.compressed:
            report["compressed_datagrams"] += 1
            if encoded[4:] == original_stream:
                report["compressed_streams_identical"] += 1
            original_block = payload[4:]
            canonical_block = compress_message_stream(original_stream)
            report["lz4_original_bytes"] += len(original_block)
            report["lz4_canonical_bytes"] += len(canonical_block)
            if canonical_block == original_block:
                report["lz4_canonical_identical"] += 1
            else:
                report["lz4_canonical_different"] += 1
                if "canonical LZ4 block" not in report["first_differences"]:
                    report["first_differences"]["canonical LZ4 block"] = _difference(
                        original_block, canonical_block, 4
                    )
    return report


def print_report(report):
    print(f"ledger: {report['ledger']}")
    print(f"  datagrams tested: {report['datagrams_tested']}")
    print(f"  datagrams identical: {report['datagrams_identical']}")
    print(
        "  identical after decompression: "
        f"{report['compressed_streams_identical']}/{report['compressed_datagrams']} "
        "compressed message streams"
    )
    print(
        "  message streams identical: "
        f"{report['message_streams_identical']}/{report['datagrams_tested']}"
    )
    print(f"  datagrams different: {report['datagrams_different']}")
    print(
        "  lz4.block.compress exact: "
        f"{report['lz4_canonical_identical']}/{report['compressed_datagrams']}"
    )
    print(
        "  lz4.block.compress different: "
        f"{report['lz4_canonical_different']}/{report['compressed_datagrams']} "
        f"(original bytes={report['lz4_original_bytes']}, "
        f"recompressed bytes={report['lz4_canonical_bytes']})"
    )
    for failure_class, count in sorted(report["difference_classes"].items()):
        print(f"  mismatch class: {failure_class}: {count}")
    for failure_class, difference in report["first_differences"].items():
        print(f"  first difference [{failure_class}]: {difference}")


def check():
    for path in CAPTURES:
        assert path.is_file(), path
        report = analyze_ledger(path)
        print_report(report)
        assert report["datagrams_tested"] > 0
        assert (report["datagrams_identical"] + report["datagrams_different"]
                == report["datagrams_tested"])
        assert report["message_streams_identical"] == report["datagrams_tested"]
        assert report["compressed_streams_identical"] == report["compressed_datagrams"]
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv != ["--check"]:
        raise SystemExit("usage: encode_carrier.py --check")
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
