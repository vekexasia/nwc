"""Plain-assert checks for the Carrier datagram encoder."""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
if str(HERE.parent.parent) not in sys.path:
    sys.path.insert(0, str(HERE.parent.parent))

import lz4.block  # noqa: E402
from decode_dtls_ledger import (  # noqa: E402
    CarrierMessage,
    Datagram,
    decode_record,
)
from encode_carrier import (  # noqa: E402
    encode_datagram,
    encode_message_stream,
    check,
)


def _assert_raises(error, function, *args):
    try:
        function(*args)
    except error:
        return
    assert False, f"expected {error.__name__}"


def _messages():
    return [
        CarrierMessage(
            flags=0x25,
            data_size=3,
            channel=1,
            num_chunks=2,
            seq=0xFFFF,
            rel_seq=0x1234,
            payload=b"abc",
        ),
        CarrierMessage(
            flags=0x28,
            data_size=2,
            channel=3,
            seq=0,
            rel_seq=0x1235,
            payload=b"de",
        ),
        CarrierMessage(
            flags=0x38,
            data_size=0,
            channel=0,
            seq=1,
            rel_seq=0x1236,
            payload=b"",
        ),
    ]


def _datagram(messages, compressed=False, trailer=b""):
    return Datagram(
        ts_ms=1,
        dir="in",
        ssl_ptr=2,
        record_idx=3,
        raw_len=0,
        mode_byte=0x81 if compressed else 0x80,
        format_byte=0x01,
        dgram_seq=0xBEEF,
        compressed=compressed,
        decompressed_len=None,
        additional_header=None,
        messages=messages,
        trailer=trailer,
    )


def _check_message_field_order():
    datagram = _datagram(_messages())
    encoded = encode_datagram(datagram)
    assert encoded == bytes.fromhex(
        "8001beef250003010002ffff1234616263"
        "2800020312356465"
        "38000000"
    )
    assert encode_message_stream(datagram) == encoded[4:]

    decoded = decode_record(3, 0, 1, 2, encoded)
    assert decoded.error is None
    assert decoded.carrier_error is None
    assert decoded.messages == _messages()


def _check_trailer_is_preserved():
    datagram = _datagram(_messages(), trailer=b"\xaa\xbb")
    encoded = encode_datagram(datagram)
    assert encoded.endswith(b"\xaa\xbb")
    decoded = decode_record(3, 0, 1, 2, encoded)
    assert decoded.carrier_error == "truncated carrier header"
    assert decoded.trailer == b"\xaa\xbb"


def _check_compressed_falls_back_to_uncompressed():
    datagram = _datagram(_messages())
    stream = encode_message_stream(datagram)
    original = b"\x81\x01\xbe\xef" + lz4.block.compress(stream, store_size=False)
    decoded = decode_record(3, 0, 1, 2, original)
    assert decoded.compressed
    assert decoded.error is None
    assert encode_datagram(decoded) == b"\x80\x01\xbe\xef" + stream


def _check_validation():
    bad_size = _messages()
    bad_size[0].data_size = 2
    _assert_raises(ValueError, encode_datagram, _datagram(bad_size))

    bad_flags = _messages()
    bad_flags[0].flags |= 0x02
    _assert_raises(ValueError, encode_datagram, _datagram(bad_flags))

    bad_mode = _datagram(_messages())
    bad_mode.error = "too-short"
    _assert_raises(ValueError, encode_datagram, bad_mode)


def main():
    _check_message_field_order()
    _check_trailer_is_preserved()
    _check_compressed_falls_back_to_uncompressed()
    _check_validation()
    check()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
