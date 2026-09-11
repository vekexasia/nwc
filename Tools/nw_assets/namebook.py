"""Build the name book: crc32(lowercase id) -> id string, from every datasheet of the game.

The wire identifies abilities (CooldownTimers), and presumably items, status effects and vitals rows,
by the CRC32 of the lowercase id string: all seven cooldown ids captured on 2026-09-11 resolved that
way against the weapon ability sheets (Ability_VoidGauntlet_Scream = 9d35d4b6, ...). This script
extracts the datatables from the paks (Oodle, see pak_extract.py), reads every string cell that looks
like an identifier and writes private/assets/namebook.json: {"9d35d4b6": "Ability_VoidGauntlet_Scream"}
plus, per id, the sheet it came from and a display name when the sheet has one.

    namebook.py build            # extract (once, ~215 MB of sheets) and write the book
    namebook.py lookup HEX...    # resolve ids
"""
import json
import re
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from datasheet import read  # noqa: E402
import pak_extract  # noqa: E402

BOOK = pak_extract.OUT / "namebook.json"
LOC = pak_extract.OUT / "localization/en-us"
SHEETS = pak_extract.OUT / "sharedassets/springboardentitites/datatables"
IDENT = re.compile(r"^[A-Za-z0-9_.\-+:]{2,96}$")
NAME_COLUMNS = ("DisplayName", "Name", "Description")


def crc(text: str) -> str:
    return f"{zlib.crc32(text.lower().encode()):08x}"


def extract(pak_glob: str, pattern: str, minimum: int, root: Path) -> None:
    if root.exists() and len(list(root.rglob("*"))) >= minimum:
        return
    decompress = pak_extract.oodle()
    for pak in pak_extract.paks(pak_glob):
        for info in pak_extract.matching(pak, [pattern]):
            target = pak_extract.OUT / info.filename
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(pak_extract.read_entry(pak, info, decompress))


def localization() -> dict:
    """English strings, '@key' -> text, from localization/en-us/*.loc.xml (184 files, 25 MB)."""
    extract("*.pak", r"^localization/en-us/.*\.loc\.xml$", 100, LOC)
    strings = {}
    for path in LOC.glob("*.loc.xml"):
        for match in re.finditer(r'<string key="([^"]+)"[^>]*>(.*?)</string>', path.read_text("utf-8", "replace"), re.S):
            strings[match.group(1).lower()] = match.group(2)
    return strings


def build() -> dict:
    extract("SharedDataStrm*.pak", r"datatables/.*\.datasheet$", 100, SHEETS)
    strings = localization()
    book = {}
    for path in sorted(SHEETS.rglob("*.datasheet")):
        try:
            sheet = read(path)
        except Exception as error:      # noqa: BLE001 - one bad sheet must not lose the book
            print(f"skip {path.name}: {error}", file=sys.stderr)
            continue
        columns = sheet["columns"]
        name_index = next((columns.index(c) for c in NAME_COLUMNS if c in columns), None)
        for row in sheet["rows"]:
            display = row[name_index] if name_index is not None else ""
            for column, value in zip(columns, row):
                if isinstance(value, str) and IDENT.match(value) and not value.startswith("@"):
                    key = crc(value)
                    text = strings.get(display[1:].lower(), "") if isinstance(display, str) and display.startswith("@") else ""
                    # the sheet that names the row wins over one that merely references the id
                    if key not in book or (text and not book[key]["text"]):
                        book[key] = {"id": value, "sheet": path.stem.replace("javelindata_", ""),
                                     "column": column, "display": display if isinstance(display, str) else "", "text": text}
    BOOK.write_text(json.dumps(book, separators=(",", ":")))
    return book


def load() -> dict:
    try:
        return json.loads(BOOK.read_text())
    except OSError:
        return {}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] == "build":
        book = build()
        print(f"{len(book)} ids -> {BOOK}")
        return 0
    if argv[0] == "lookup":
        book = load()
        for key in argv[1:]:
            print(key, book.get(key.lower().removeprefix("0x"), "-"))
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
