#!/usr/bin/env python3
"""Open the New World Ghidra project once and answer questions in seconds.

    # interactive session (one project open, then type queries)
    .venv-ghidra/bin/python Tools/nw_capture/experimental/offline/ghidra/nw_ghidra.py
    >>> print(table(0x142a35db0))          # property table of a schema builder
    >>> save(decompile(0x142a35db0))       # big outputs go to a file, not to stdout
    >>> symbols("ALCReplicatedState")[:5]

    # non-interactive
    .venv-ghidra/bin/python .../nw_ghidra.py --exec 'print(len(decompile(0x142a35db0).splitlines()))'
    .venv-ghidra/bin/python .../nw_ghidra.py --script /tmp/query.py

Why a session: a warm analyzeHeadless run is 2-3 s, but this is 1.2 s to start, 0.9 s to
open the program and ~0.3 s per decompilation, with no Java script compilation and no
per-question project reload. The JDK probe of PyGhidra is bypassed on purpose: it would
write the JDK path into the Ghidra installation.

Environment overrides: GHIDRA_INSTALL_DIR, JAVA_HOME, NW_GHIDRA_HOME (isolated Ghidra user
home, defaults to ~/.cache/nw-ghidra), NW_GHIDRA_PROJECT (default ~/ghidra-projects),
NW_GHIDRA_PROGRAM (default NewWorld.exe), NW_GHIDRA_DUMPS (default /tmp/nw-ghidra-dumps).
"""
from __future__ import annotations

import argparse
import code
import os
import re
import sys
import time
from pathlib import Path

DEFAULT_GHIDRA = Path.home() / ".local/share/ghidra/ghidra_12.1.3_PUBLIC"
JDK_SEARCH = (Path.home() / ".local/share/mise/installs/java", Path("/usr/lib/jvm"))


def find_jdk() -> Path:
    from_env = os.environ.get("JAVA_HOME")
    if from_env and (Path(from_env) / "bin/java").exists() and "21" in from_env:
        return Path(from_env)
    for root in JDK_SEARCH:
        if not root.is_dir():
            continue
        for entry in sorted(root.glob("*21*")):
            if (entry / "bin/java").exists():
                return entry
    raise SystemExit("JDK 21 not found; set JAVA_HOME to a Java 21 installation")


def wait_for_project_slot():
    """A Ghidra project allows one session at a time: queue on a lock file instead of failing."""
    import fcntl
    path = os.environ.get("NW_GHIDRA_LOCK", "/tmp/nw-ghidra.lock")
    handle = open(path, "w")
    deadline = time.monotonic() + float(os.environ.get("NW_GHIDRA_LOCK_WAIT", "600"))
    waited = False
    while True:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if waited:
                print(f"project slot acquired after waiting")
            return handle
        except OSError:
            if not waited:
                print(f"waiting for the Ghidra project lock (another session holds it, {path})")
                waited = True
            if time.monotonic() > deadline:
                raise SystemExit("timed out waiting for the Ghidra project lock")
            time.sleep(1.0)


def start_ghidra():
    ghidra = Path(os.environ.get("GHIDRA_INSTALL_DIR", DEFAULT_GHIDRA))
    if not (ghidra / "support/analyzeHeadless").exists():
        raise SystemExit(f"GHIDRA_INSTALL_DIR does not look like a Ghidra install: {ghidra}")
    os.environ["GHIDRA_INSTALL_DIR"] = str(ghidra)
    os.environ["_JAVA_OPTIONS"] = f"-Duser.home={Path(os.environ.get('NW_GHIDRA_HOME', Path.home() / '.cache/nw-ghidra'))}"
    slot = wait_for_project_slot()
    from pyghidra.launcher import HeadlessPyGhidraLauncher

    launcher = HeadlessPyGhidraLauncher(verbose=False, install_dir=ghidra)
    launcher.java_home = find_jdk()
    launcher.start()

    from ghidra.base.project import GhidraProject

    project_dir = Path(os.environ.get("NW_GHIDRA_PROJECT", Path.home() / "ghidra-projects"))
    deadline = time.monotonic() + float(os.environ.get("NW_GHIDRA_LOCK_WAIT", "600"))
    while True:
        try:
            project = GhidraProject.openProject(str(project_dir), "nw", False)
            break
        except Exception as error:  # another session (possibly one that ignores the flock) holds it
            if time.monotonic() > deadline:
                raise SystemExit(f"project still locked after waiting: {error}")
            print("project locked by another session, retrying in 2 s")
            time.sleep(2)
    program = project.openProgram("/", os.environ.get("NW_GHIDRA_PROGRAM", "NewWorld.exe"), True)
    return project, program, slot


def build_namespace(project, program):
    from ghidra.app.decompiler import DecompInterface
    from ghidra.util.task import ConsoleTaskMonitor
    import jpype

    space = program.getAddressFactory().getDefaultAddressSpace()
    decompiler = DecompInterface()
    decompiler.openProgram(program)
    monitor = ConsoleTaskMonitor()
    dumps = Path(os.environ.get("NW_GHIDRA_DUMPS", "/tmp/nw-ghidra-dumps"))

    def to_va(value) -> "ghidra.program.model.address.Address":
        return space.getAddress(int(value))

    def decompile(va, timeout: int = 120) -> str:
        """Decompiled C of the function starting at va."""
        function = program.getFunctionManager().getFunctionAt(to_va(va))
        if function is None:
            return f"<no function at {va:#x}>"
        result = decompiler.decompileFunction(function, timeout, monitor)
        return result.getDecompiledFunction().getC() if result.decompileCompleted() else "<decompile failed>"

    def listing(va, count: int = 40) -> str:
        """First `count` instructions at va."""
        out, address = [], to_va(va)
        for _ in range(count):
            instruction = program.getListing().getInstructionAt(address)
            if instruction is None:
                break
            out.append(f"{instruction.getAddress()}  {instruction}")
            address = instruction.getAddress().add(instruction.getLength())
        return "\n".join(out)

    def xrefs(va) -> list:
        """Addresses that reference va."""
        return [str(ref.getFromAddress()) for ref in program.getReferenceManager().getReferencesTo(to_va(va))]

    def symbols(needle: str, limit: int = 50) -> list:
        """Symbols whose name contains needle (case insensitive). Full-table scan, a few seconds."""
        out = []
        for symbol in program.getSymbolTable().getAllSymbols(True):
            if needle.lower() in symbol.getName().lower():
                out.append((symbol.getName(), str(symbol.getAddress())))
                if len(out) >= limit:
                    break
        return out

    def find_bytes(pattern: bytes, limit: int = 50) -> list:
        """Addresses where the byte pattern occurs in any memory block."""
        signed = [b - 256 if b > 127 else b for b in pattern]  # JByte is signed
        java_bytes = jpype.JArray(jpype.JByte)(signed)
        out = []
        memory = program.getMemory()
        for block in memory.getBlocks():
            address = block.getStart()
            while len(out) < limit:
                found = memory.findBytes(address, java_bytes, None, True, monitor)
                if found is None or not block.contains(found):
                    break
                out.append(str(found))
                address = found.add(1)
        return out

    def strings(needle: str, limit: int = 50) -> list:
        """Addresses of an ASCII pattern (type names, property names)."""
        return find_bytes(needle.encode("ascii"), limit)

    def read_qword(va) -> int:
        """Little-endian qword at va, or -1 if unreadable."""
        buffer = jpype.JArray(jpype.JByte)(8)
        try:
            program.getMemory().getBytes(to_va(va), buffer)
        except Exception:
            return -1
        return int.from_bytes(bytes((b & 0xFF) for b in buffer), "little")

    def read_ascii(va, length: int = 32) -> str:
        from ghidra.program.model.mem import Memory
        buffer = jpype.JArray(jpype.JByte)(length)
        try:
            program.getMemory().getBytes(to_va(va), buffer)
        except Exception:
            return "?"
        out = []
        for byte in bytes((b & 0xFF) for b in buffer):
            if byte == 0 or byte < 0x20 or byte > 0x7E:
                break
            out.append(chr(byte))
        return "".join(out)

    def table(builder_va, verbose: bool = True) -> list:
        """Property table of a schema builder: bit order, member offset, name, descriptor, reader."""
        from ghidra.program.model.address import Address
        c = decompile(builder_va)
        descriptors = {}
        for match in re.finditer(r"param_1\[(0x[0-9a-f]+|\d+)\]\s*=\s*&(UNK_[0-9a-f]+);", c):
            index = int(match.group(1), 16) if match.group(1).startswith("0x") else int(match.group(1))
            descriptors[index * 8] = match.group(2)[4:]
        rows = []
        pattern = re.compile(r"\*puVar3 = &(UNK_[0-9a-f]+);\s*\n\s*puVar3\[1\] = param_1 \+ (0x[0-9a-f]+|\d+);")
        for bit, match in enumerate(pattern.finditer(c)):
            offset = int(match.group(2), 16) if match.group(2).startswith("0x") else int(match.group(2))
            offset *= 8
            name_va = int(match.group(1)[4:], 16)
            descriptor = descriptors.get(offset)
            reader = None
            if descriptor:
                buffer = jpype.JArray(jpype.JByte)(8)
                try:
                    program.getMemory().getBytes(to_va(int(descriptor, 16) + 0x30), buffer)
                    reader = int.from_bytes(bytes((b & 0xFF) for b in buffer), "little")
                except Exception:
                    reader = None
            rows.append({"bit": bit, "member": offset, "name": read_ascii(name_va, 40),
                         "descriptor": descriptor, "reader": None if reader is None else f"0x{reader:x}"})
        if verbose:
            print(f"builder {builder_va:#x} -> {len(rows)} properties, {len(descriptors)} descriptor slots")
            print(f"{'bit':>3} {'member':>9} {'name':<26} {'descriptor':<14} {'reader':<12}")
            for row in rows:
                print(f"{row['bit']:>3} +0x{row['member']:<6x} {str(row['name']):<26} "
                      f"{('0x' + row['descriptor']) if row['descriptor'] else '-':<14} {row['reader'] or '-':<12}")
        return rows

    def save(text: str, name: str = "dump.txt") -> str:
        """Write a big answer to a file instead of printing it."""
        dumps.mkdir(parents=True, exist_ok=True)
        path = dumps / name
        path.write_text(text)
        print(f"wrote {len(text)} bytes to {path}")
        return str(path)

    return {
        "project": project, "program": program, "p": program,
        "decompile": decompile, "listing": listing, "xrefs": xrefs,
        "symbols": symbols, "strings": strings, "find_bytes": find_bytes, "table": table, "save": save,
        "read_ascii": read_ascii, "read_qword": read_qword, "to_va": to_va,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--exec", dest="expr", action="append", help="evaluate this and exit (repeatable)")
    parser.add_argument("--script", type=Path, help="run this python file with the helpers in scope")
    args = parser.parse_args(argv)

    project, program, slot = start_ghidra()
    namespace = build_namespace(project, program)
    try:
        if args.script:
            exec(compile(args.script.read_text(), str(args.script), "exec"), namespace)
        for expr in args.expr or []:
            exec(compile(expr, "<--exec>", "exec"), namespace)
        if not args.script and not args.expr:
            banner = ("Ghidra session ready: program, p, decompile(va), listing(va), xrefs(va), "
                      "symbols(needle), strings(needle), find_bytes(pat), table(builder_va), save(text, name)")
            code.interact(banner=banner, local=namespace)
    finally:
        try:
            project.close()
        except Exception:
            pass
        try:
            slot.close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
