#!/usr/bin/env python3
"""Census of the replicated states: name and typeIndex from the community triage report,
uuid / registry index / Marshal+Unmarshal addresses from the local registry dump.

Read-only. Both sources are gitignored, under private/open-world-discord/attachments/:

  * 211_capture-triage.html   community message catalog: type_idx, name, message_kind, seen
  * 087_typeregistry.json     3487 entries (typeIndex, index, uuid, handler addresses); it
                              carries no name for any *ReplicatedState entry, so the catalog
                              above is the naming source

The registry addresses are valid for our build, checked on ALC only: typeIndex 11 Unmarshal is
NewWorld+0x2a327f0, which our static analysis names FUN_142a327f0
(docs/Network/alc-static-analysis.md:50).

Usage:
  .venv-capture/bin/python Tools/nw_capture/experimental/offline/list_replicated_states.py
  ... --missing   only the states never seen in the community corpus
  ... --tsv       machine-readable
  ... --check     assert the invariants docs/Network/replicated-state-todo.md relies on
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
ATTACH = REPO / "private" / "open-world-discord" / "attachments"
TRIAGE = ATTACH / "211_capture-triage.html"
REGISTRY = ATTACH / "087_typeregistry.json"

ENTRY_RE = re.compile(r'\{"type_idx":\d+,"name":"[^"]*".*?\}(?=,\{|\])')


def catalog_rows(path=TRIAGE):
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    rows = []
    for raw in ENTRY_RE.findall(text):
        entry = json.loads(raw)
        if entry.get("message_kind") == "replicated state":
            rows.append(entry)
    return sorted(rows, key=lambda row: row["type_idx"])


def registry_by_type(path=REGISTRY):
    data = json.loads(Path(path).read_text())["data"]
    return {entry["typeIndex"]: entry for _uuid, entry in data["m_list"]}


def join():
    registry = registry_by_type()
    rows = []
    for entry in catalog_rows():
        record = registry.get(entry["type_idx"], {})
        rows.append({
            "typeIndex": entry["type_idx"],
            "name": entry["name"],
            "seen": entry["seen"],
            "count": entry["count"],
            "registryIndex": record.get("index"),
            "uuid": record.get("uuid", ""),
            "unmarshal": record.get("handler", {}).get("Unmarshal", ""),
        })
    return rows


def print_rows(rows, tsv=False):
    if tsv:
        print("typeIndex\tseen\tcount\tregistryIndex\tunmarshal\tuuid\tname")
    for row in rows:
        if tsv:
            print("\t".join(str(row[key]) for key in
                            ("typeIndex", "seen", "count", "registryIndex",
                             "unmarshal", "uuid", "name")))
        else:
            print(f'{row["typeIndex"]:>5}  {"seen" if row["seen"] else "MISSING":<7} '
                  f'{row["count"]:>9}  {row["unmarshal"]:<20} {row["name"]}')


def check(rows):
    """Invariants the TODO doc quotes. Fails loudly if the sources or the join change."""
    assert len(rows) == 130, f"expected 130 replicated states, got {len(rows)}"
    by_type = {row["typeIndex"]: row for row in rows}
    alc = by_type[11]
    assert alc["name"] == "MB::ALCReplicatedState", alc
    assert alc["uuid"] == "01B0664B-3AB6-44A6-87E3-8C69D40E0365", alc
    assert alc["unmarshal"] == "NewWorld+0x2a327f0", alc
    assert by_type[13]["name"] == "MB::PositionInTheWorldReplicatedState", by_type[13]
    assert by_type[3935]["name"] == "MB::PlayerComponentReplicatedState", by_type[3935]
    missing = [row for row in rows if not row["seen"]]
    assert len(missing) == 13, f"expected 13 never-seen states, got {len(missing)}"
    assert all(row["registryIndex"] is not None for row in rows), "typeIndex missing from registry"
    print(f"ok: 130 replicated states, 13 never seen, ALC unmarshal {alc['unmarshal']}")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--missing", action="store_true", help="only never-seen states")
    parser.add_argument("--tsv", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    rows = join()
    if args.check:
        check(rows)
        return 0
    print_rows([row for row in rows if not row["seen"]] if args.missing else rows, args.tsv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
