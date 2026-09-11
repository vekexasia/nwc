"""List and extract entries of the game's .pak files (zip containers, entries stored or Oodle-compressed).

The Oodle decompressor is a third-party binary and stays out of the repository: point NW_OODLE_LIB at
liboo2corelinux64.so.9 (default private/tools/oodle/liboo2corelinux64.so.9). The game install is read
only; extracted files go under private/assets/ (gitignored) unless --out says otherwise.

    pak_extract.py list  [--pak GLOB] PATTERN...           # entry names matching any regex
    pak_extract.py get   [--pak GLOB] [--out DIR] PATTERN... # extract the matching entries

Read first from a community pass on 2026-09-11: SharedDataStrm-part7.pak holds the player CAGE grid
and action lists, SharedDataStrm.pak the Mannequin ADBs; zip method 15 is Oodle, 0 is stored.
"""
import argparse
import ctypes
import os
import re
import struct
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GAME = Path(os.environ.get("NW_GAME_DIR", os.path.expanduser("~/.local/share/Steam/steamapps/common/New World")))
OODLE = Path(os.environ.get("NW_OODLE_LIB", REPO / "private/tools/oodle/liboo2corelinux64.so.9"))
OUT = REPO / "private/assets"


def paks(glob: str):
    return sorted((GAME / "assets").glob(glob))


def matching(pak: Path, patterns):
    with zipfile.ZipFile(pak) as archive:
        for info in archive.infolist():
            if any(re.search(p, info.filename, re.I) for p in patterns):
                yield info


def oodle():
    lib = ctypes.CDLL(str(OODLE))
    fn = lib.OodleLZ_Decompress
    fn.argtypes = [ctypes.c_void_p, ctypes.c_ssize_t, ctypes.c_void_p, ctypes.c_ssize_t, ctypes.c_int32,
                   ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p, ctypes.c_ssize_t, ctypes.c_void_p,
                   ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ssize_t, ctypes.c_int32]
    fn.restype = ctypes.c_ssize_t
    return fn


def read_entry(pak: Path, info: zipfile.ZipInfo, decompress) -> bytes:
    if info.compress_type == 0:
        with zipfile.ZipFile(pak) as archive:
            return archive.read(info)
    if info.compress_type != 15:
        raise ValueError(f"{info.filename}: zip method {info.compress_type} is neither stored nor Oodle")
    with open(pak, "rb") as handle:
        handle.seek(info.header_offset)
        sig, _v, _f, method, _t, _d, _crc, _cs, _us, name_len, extra_len = struct.unpack("<IHHHHHIIIHH", handle.read(30))
        assert sig == 0x04034B50 and method == 15, info.filename
        handle.seek(name_len + extra_len, 1)
        compressed = handle.read(info.compress_size)
    out = ctypes.create_string_buffer(info.file_size)
    written = decompress(compressed, len(compressed), out, info.file_size, 1, 0, 0, None, 0, None, None, None, 0, 3)
    if written != info.file_size:
        raise ValueError(f"{info.filename}: Oodle returned {written}, expected {info.file_size}")
    return out.raw


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("list", "get"))
    parser.add_argument("patterns", nargs="+", help="regexes on the entry name, case-insensitive")
    parser.add_argument("--pak", default="*.pak", help="glob under <game>/assets, default all")
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args(argv)
    shown = 0
    decompress = oodle() if args.command == "get" else None
    for pak in paks(args.pak):
        for info in matching(pak, args.patterns):
            if args.command == "list":
                print(f"{pak.name}\t{info.compress_type}\t{info.file_size}\t{info.filename}")
            else:
                data = read_entry(pak, info, decompress)
                target = args.out / info.filename
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                print(f"{target} ({len(data)} bytes)")
            shown += 1
            if shown >= args.limit:
                print(f"-- limit {args.limit} reached", file=sys.stderr)
                return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
