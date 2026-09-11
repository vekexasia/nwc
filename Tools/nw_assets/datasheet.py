"""Read a New World .datasheet (the binary tables behind javelindata_*.datasheet).

Layout as documented by new-world-tools (datasheet/parser.go), checked here on the extracted sheets:

    header, 15 x u32 LE: signature, uniqueId crc32, uniqueId offset, type crc32, type offset, ?,
                         body length, 7 x ?, body offset
    meta:   ?, ?, column count, row count, 4 x ?
    columns: count x (crc32, name offset, type: 1 string, 2 number, 3 boolean)
    cells:   rows x columns x (offset, value)
    worksheet name, then the string pool
    every offset is relative to 60 + body offset

Strings are read at their offset; for number and boolean columns the second u32 of the cell is the
value (float32 for numbers, 0/1 for booleans), which is what the string at the offset spells too.

    datasheet.py FILE [--csv] [--grep REGEX]
"""
import argparse
import csv
import re
import struct
import sys
from pathlib import Path

HEADER = 15 * 4


def read(path: Path):
    data = path.read_bytes()
    header = struct.unpack_from("<15I", data, 0)
    body = HEADER + header[14]
    _f2, _f3, columns, rows = struct.unpack_from("<4I", data, HEADER)
    pos = HEADER + 8 * 4

    def string_at(offset):
        start = body + offset
        end = data.index(b"\x00", start)
        return data[start:end].decode("utf-8", "replace")

    column_defs = []
    for _ in range(columns):
        _crc, offset, kind = struct.unpack_from("<3I", data, pos)
        pos += 12
        column_defs.append((string_at(offset), kind))
    table = []
    for _ in range(rows):
        row = []
        for name, kind in column_defs:
            offset, raw = struct.unpack_from("<II", data, pos)
            pos += 8
            if kind == 2:
                row.append(struct.unpack("<f", struct.pack("<I", raw))[0])
            elif kind == 3:
                row.append(bool(raw))
            else:
                row.append(string_at(offset))
        table.append(row)
    worksheet = data[pos:data.index(b"\x00", pos)].decode("utf-8", "replace")
    return {"type": string_at(header[4]), "unique_id": string_at(header[2]), "worksheet": worksheet,
            "columns": [name for name, _ in column_defs], "types": [kind for _, kind in column_defs], "rows": table}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", type=Path)
    parser.add_argument("--csv", action="store_true")
    parser.add_argument("--grep", help="only rows whose cells match this regex")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args(argv)
    sheet = read(args.file)
    rows = sheet["rows"]
    if args.grep:
        rows = [r for r in rows if any(re.search(args.grep, str(c), re.I) for c in r)]
    if args.csv:
        writer = csv.writer(sys.stdout)
        writer.writerow(sheet["columns"])
        writer.writerows(rows)
        return 0
    print(f"{sheet['type']} / {sheet['unique_id']} / worksheet {sheet['worksheet']}: "
          f"{len(sheet['columns'])} columns, {len(sheet['rows'])} rows")
    print("columns:", ", ".join(sheet["columns"]))
    for row in rows[:args.limit]:
        print({c: v for c, v in zip(sheet["columns"], row) if v not in ("", 0.0, False)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
