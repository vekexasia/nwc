# Ghidra workflow for this project

How to interrogate `NewWorld.exe` without paying minutes per question. Numbers measured on this
machine (project `~/ghidra-projects/nw.gpr`, 183 MB binary, 468 MB project database).

| operation | measured cost |
|---|---|
| `analyzeHeadless`, warm project, 3 scripts in one run | 3 s |
| `analyzeHeadless`, warm project, 1 script | 2 s |
| `analyzeHeadless`, first run after boot (cold) | minutes |
| PyGhidra session start (JVM + Ghidra) | 1.2 s |
| PyGhidra: open the program read-only | 0.9 s |
| PyGhidra: decompile `FUN_142a35db0` (523 lines) | 0.2-0.3 s |

The expensive part is not Ghidra. It is a script that dumps a 100 KB disassembly and an agent that
then reads it: that is where an hour and real money went. A script must answer.

## Rules

- **Batch.** Several `-postScript` arguments in one `analyzeHeadless` invocation, not one run per
  question. Never two headless sessions at once.
- **The script answers, it does not dump.** Have it do the join and print the compact result
  (table, address, verdict, a few KB). Raw listings and decompilations go to a file under `/tmp` or
  `private/`, and are read only when the compact answer is not enough.
- **Extract once, query offline.** Schema tables, descriptor/reader maps and decompilations belong in
  a cache (`private/decoder-state/ghidra-alc/` is the example), queried with rg/python.
- **Ghidra is for names and structure.** For the wire, a runtime hook (reader plus destination
  pointer) is faster and cheaper; see `docs/Network/alc-protocol-reference.md` section 2.4.
- Before asking Ghidra anything, check whether the answer is already in `docs/Network/`.

## Interactive session (PyGhidra)

```
python3 -m venv .venv-ghidra
.venv-ghidra/bin/pip install pyghidra==3.1.0          # requires Ghidra >= 12.0
.venv-ghidra/bin/python Tools/nw_capture/experimental/offline/ghidra/nw_ghidra.py
```

Helpers in the session: `program`/`p`, `decompile(va)`, `listing(va, n)`, `xrefs(va)`,
`symbols(needle)`, `strings(needle)`, `find_bytes(pattern)`, `read_ascii(va)`, `read_qword(va)`,
`table(builder_va)` (property table of a schema builder), `save(text, name)` (route big output to a
file). Non-interactive: `--exec '<python>'` or `--script file.py`.

The wrapper sets `launcher.java_home` before `start()` on purpose: PyGhidra's own JDK probe would
write the JDK path into the Ghidra installation. It also points the Ghidra user home at
`~/.cache/nw-ghidra` so the operator's `~/.config/ghidra` is untouched. Overrides:
`GHIDRA_INSTALL_DIR`, `JAVA_HOME`, `NW_GHIDRA_HOME`, `NW_GHIDRA_PROJECT`, `NW_GHIDRA_PROGRAM`,
`NW_GHIDRA_DUMPS`.

## Turning a name into a field table

`SchemaTable.java` (or `table(va)` in the session) takes the address of a schema builder and prints
bit order, member offset, property name, descriptor and reader:

```
.venv-ghidra/bin/python .../nw_ghidra.py --exec 'table(0x142a35db0)'
builder 0x142a35db0 -> 63 properties, 72 descriptor slots
bit    member name                       descriptor     reader
  0 +0x7d8    idRel                      0x1480ff310    0x142a42d40
```

## Finding a type by name

Registry type names live in `.rdata` as plain ASCII; some also appear UTF-16LE in handler objects.
Search them with `strings(name)`; a name absent in ASCII should also be tried UTF-16LE and as
variants, because the build in hand may not match the community dumps:

```
strings("ALCReplicatedState")      -> 1480fed90, 1480ffa68, 14a18abee
strings("VitalsReplicatedState")   -> nothing (name from an older/other build)
strings("VitalsState")             -> 1480a0428, 1480a0443, 1480a0575
strings("MaxHealth")               -> 14839aff8, ...
```

Once the name address is known, walk back through the qwords before it to find the descriptor that
holds the pointer to that name (the ALC descriptor does this at `+0x00` with the name 0x1d0 further
on), then read the descriptor's own pointers: `+0x30` is the field reader in the property-type
blocks, and the schema builder that writes the property list is reached the same way the ALC table
was (see section 8 of `alc-static-analysis.md`).
