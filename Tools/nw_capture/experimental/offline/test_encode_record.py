#!/usr/bin/env python3
"""Plain-assert checks for the frame and record encoder."""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from encode_record import check, encode_frame  # noqa: E402


def _assert_raises(error, function, *args):
    try:
        function(*args)
    except error:
        return
    assert False, f"expected {error.__name__}"


def _check_frame_boundaries():
    assert encode_frame(0, b"\x01\x02\x03\x04", b"", 0) == bytes.fromhex(
        "000108010000000001020304000000"
    )
    assert encode_frame(0xFFFFFFFF, memoryview(b"1234"), b"body", 0x40087).endswith(
        bytes.fromhex("626f6479c72004")
    )
    _assert_raises(ValueError, encode_frame, 0, b"123", b"", 0)
    _assert_raises(ValueError, encode_frame, -1, b"1234", b"", 0)
    _assert_raises(ValueError, encode_frame, 0, b"1234", b"x" * 65536, 0)
    _assert_raises(ValueError, encode_frame, 0, b"1234", b"", 1 << 35)

def main():
    _check_frame_boundaries()
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
