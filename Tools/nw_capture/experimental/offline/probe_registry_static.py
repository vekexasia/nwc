#!/usr/bin/env python3
"""Static checks against our own NewWorld.exe, no decompiler.

Two jobs:

  --check-build   Does the community registry dump describe our build? Compares the 3487
                  uuids and the 312 names of 087_typeregistry.json against the literal
                  strings in the local NewWorld.exe (case-insensitive).
  --record NAME   Finds the literal string NAME in the executable, looks for 8-byte pointers
                  to it, and dumps the surrounding qwords with every pointer resolved to a
                  section (and to a string when it points at one). Use it to locate the
                  static descriptors for types the community dump never covered, such as
                  ALCReplicatedState.

Read-only. Nothing is executed from the binary and nothing is written.
"""
from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

DEFAULT_EXE = Path("~/.local/share/Steam/steamapps/common/New World/Bin64/NewWorld.exe")
REPO = Path(__file__).resolve().parents[4]
DEFAULT_REG = REPO / "private" / "open-world-discord" / "attachments" / "087_typeregistry.json"


def parse_pe(data):
    pe_off = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe_off:pe_off + 4] != b"PE\0\0":
        raise ValueError("not a PE file")
    num_sections = struct.unpack_from("<H", data, pe_off + 6)[0]
    opt_size = struct.unpack_from("<H", data, pe_off + 20)[0]
    opt_off = pe_off + 24
    magic = struct.unpack_from("<H", data, opt_off)[0]
    image_base = (struct.unpack_from("<Q", data, opt_off + 24)[0] if magic == 0x20B
                  else struct.unpack_from("<I", data, opt_off + 28)[0])
    sections = []
    for i in range(num_sections):
        off = opt_off + opt_size + 40 * i
        name = data[off:off + 8].rstrip(b"\0").decode("ascii", "replace")
        vaddr, vsize, raw, rawsize = struct.unpack_from("<IIII", data, off + 12)
        sections.append((name, image_base + vaddr, raw, max(vsize, rawsize)))
    return image_base, sections


class Exe:
    def __init__(self, path):
        self.data = path.read_bytes()
        self.image_base, self.sections = parse_pe(self.data)

    def va_of(self, file_offset):
        for name, base, raw, size in self.sections:
            if raw <= file_offset < raw + size:
                return base + (file_offset - raw), name
        return None, None

    def offset_of(self, va):
        for name, base, raw, size in self.sections:
            if base <= va < base + size:
                return raw + (va - base), name
        return None, None

    def string_at(self, va):
        off, _ = self.offset_of(va)
        if off is None:
            return None
        end = self.data.find(b"\0", off)
        raw = self.data[off:min(end, off + 96)]
        if len(raw) < 4 or not all(32 <= c < 127 for c in raw):
            return None
        return raw.decode("ascii")

    def check_build(self, registry):
        entries = [e[1] for e in registry["data"]["m_list"]]
        names = [e.get("name") for e in entries if e.get("name")]
        uuids = [e.get("uuid") for e in entries if e.get("uuid")]
        name_hits = sum(1 for n in names if n.encode() in self.data)
        uuid_hits = sum(1 for u in uuids
                        if u.encode() in self.data or u.lower().encode() in self.data)
        print(f"registry entries: {len(entries)}")
        print(f"  entries carrying a name: {len(names)}")
        print(f"  names present as literal strings: {name_hits}/{len(names)}")
        print(f"  uuids present (case-insensitive): {uuid_hits}/{len(uuids)}")

    def dump_record(self, name, before=0x40, after=0x120):
        text = name.encode()
        literals = []
        start = 0
        while True:
            i = self.data.find(text, start)
            if i < 0:
                break
            literals.append(i)
            start = i + 1
        print(f"\n{name}: {len(literals)} literal occurrences")
        for i in literals:
            va, sec = self.va_of(i)
            print(f"  literal at file 0x{i:x} VA 0x{va:x} ({sec})")
            refs = self.find_qwords(struct.pack("<Q", va))
            print(f"    8-byte pointers to it: {len(refs)}")
            for ref in refs[:2]:
                self.dump_words(ref - before, before + after)

    def find_qwords(self, needle):
        out, start = [], 0
        while True:
            i = self.data.find(needle, start)
            if i < 0:
                return out
            out.append(i)
            start = i + 1

    def dump_words(self, start, length):
        for i in range(0, length, 8):
            off = start + i
            q = struct.unpack_from("<Q", self.data, off)[0]
            va, _ = self.va_of(off)
            note = ""
            if self.image_base <= q < self.image_base + 0x10000000:
                _, sec = self.offset_of(q)
                target = self.string_at(q)
                note = f"-> {sec}" + (f' str={target!r}' if target else "")
            elif 0 < q <= 0xFFFFFFFF:
                note = f"u32 pair {q & 0xFFFFFFFF} / {q >> 32}"
            print(f"    +0x{i:04x} 0x{va:011x} {q:#018x} {note}")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path, default=DEFAULT_EXE)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REG)
    parser.add_argument("--record", action="append", default=[],
                        help="name literal to locate and dump (repeatable)")
    parser.add_argument("--skip-build-check", action="store_true")
    args = parser.parse_args(argv)

    exe = Exe(args.exe)
    print(f"{args.exe}\n  image base 0x{exe.image_base:x}, {len(exe.data)} bytes")
    if not args.skip_build_check:
        exe.check_build(json.load(open(args.registry, encoding="utf-8")))
    for name in (args.record or ["ALCReplicatedState"]):
        exe.dump_record(name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
