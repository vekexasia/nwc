#!/usr/bin/env python3
"""Attach to the already-running New World (Proton) and run one Frida probe with the repo's
DTLS ledger capture. Reusable wrapper around the documented attach route.

    .venv-capture/bin/python Tools/nw_capture/experimental/nw_capture_probe.py \
        --probe Tools/nw_capture/experimental/nw_field_probe.js --seconds 40 --label walktest

Writes: Tools/nw_capture/captures/<session>/dtls/ledger.bin and Tools/nw_capture/logs/<ts>_<label>.log
The game is never spawned, restarted or killed; the probe must be read-only.

One capture at a time: this takes the lock in `capture_lock.py` and waits for a running
capture instead of overlapping it, and it clears leftover frida-server processes first.
"""
from __future__ import annotations

import argparse
import contextlib
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import frida

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "Tools/nw_capture"))
from _runner import FridaRunner  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
import capture_lock  # noqa: E402

STEAM = Path.home() / ".local/share/Steam/steamapps"
RUNTIME = str(STEAM / "common/SteamLinuxRuntime_4/run")
WINE = str(STEAM / "common/Proton 11.0/files/bin/wine")
PFX = str(STEAM / "compatdata/1063730/pfx")
PORT = 27943


def game_host_pids():
    """Host PIDs of NewWorld.exe, matched on the process name so our own command line cannot match."""
    out = subprocess.run(["ps", "-eo", "pid,comm"], capture_output=True, text=True).stdout
    pids = []
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "NewWorld.exe":
            pids.append(int(parts[0]))
    return pids


def stale_agent_pids():
    """Game processes that still have a frida agent mapped: their attach always times out.

    An injected agent stays inside the target until the target restarts and cannot be unloaded from
    outside, so the only fix is a new game process. Detecting it here turns a 25 second timeout into
    an immediate, actionable message.
    """
    stale = []
    for pid in game_host_pids():
        try:
            maps = Path(f"/proc/{pid}/maps").read_text(errors="ignore")
        except OSError:
            continue
        if "frida-agent" in maps:
            stale.append(pid)
    return stale


def leftover_servers():
    """PIDs of frida-server processes left behind by a killed capture."""
    mine = {os.getpid(), os.getppid()}
    out = subprocess.run(["ps", "-eo", "pid,args"], capture_output=True, text=True).stdout
    found = []
    for line in out.splitlines()[1:]:
        pid, _, args = line.strip().partition(" ")
        if "frida-server" not in args or "grep" in args:
            continue
        if pid.isdigit() and int(pid) not in mine:
            found.append(int(pid))
    return found


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", required=True, type=Path)
    parser.add_argument("--seconds", type=float, default=40.0)
    parser.add_argument("--label", default="probe")
    parser.add_argument("--wait", type=float, default=None,
                        help="seconds to wait for a running capture (default: NW_CAPTURE_WAIT or 900)")
    args = parser.parse_args(argv)
    args.probe = args.probe.resolve()   # _runner resolves relative probes against Tools/nw_capture
    # A shell background job starts with SIGINT ignored; take it back so `kill -INT <pid>` is the clean
    # stop (KeyboardInterrupt -> detach), instead of a capture that only ends at its timeout.
    signal.signal(signal.SIGINT, signal.default_int_handler)

    try:
        lock = capture_lock.acquire(args.label, wait=args.wait)
    except capture_lock.CaptureBusy as busy:
        print(f"BLOCKED: {busy}", file=sys.stderr)
        return 1

    # Only with the lock held: a frida-server found now is a leftover, not another capture's server.
    for pid in leftover_servers():
        print(f"clearing leftover frida-server pid {pid}", flush=True)
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.kill(pid, 9)
        time.sleep(0.3)

    stale = stale_agent_pids()
    if stale:
        print("BLOCKED: NewWorld.exe already carries an injected frida agent", file=sys.stderr)
        print(f"  host pid(s): {', '.join(str(pid) for pid in stale)}", file=sys.stderr)
        print("  An agent stays inside the game until the game restarts and cannot be unloaded from",
              file=sys.stderr)
        print("  outside, so every attach would time out after 25 seconds.", file=sys.stderr)
        print("  Fix: restart the game (`steam -applaunch 1063730`) and capture again.", file=sys.stderr)
        print("  Do NOT delete .../Temp/re.frida.server instead: unlinking the file of a mapped agent",
              file=sys.stderr)
        print("  is what makes the process permanently unattachable.", file=sys.stderr)
        capture_lock.release(lock)
        return 3

    env = dict(os.environ, WINEPREFIX=PFX, WINEDEBUG="-all")
    server = subprocess.Popen([RUNTIME, "--", WINE, str(REPO / "Tools/nw_capture/frida-server.exe"),
                               "--listen", f"127.0.0.1:{PORT}"], env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              start_new_session=True)
    device = attached = None
    try:
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", PORT), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.2)
        device = frida.get_device_manager().add_remote_device(f"127.0.0.1:{PORT}")
        procs = device.enumerate_processes()
        targets = [p for p in procs if p.name.lower() == "newworld.exe"]
        servers = [p for p in procs if p.name.lower() == "frida-server.exe"]
        if len(targets) != 1 or len(servers) != 1:
            print("BLOCKED: expected one NewWorld.exe and one frida-server.exe", file=sys.stderr)
            return 1
        attached = targets[0].pid
        session = time.strftime("proton_%Y%m%d_%H%M%S") + "-" + args.label
        runner = FridaRunner(None, scripts=[str(args.probe)], timeout_s=args.seconds,
                             log_stem=args.label, session=session,
                             host=f"127.0.0.1:{PORT}", pid=attached)
        print(f"session={runner.session}")
        print(f"ledger={runner._ledger_path}")
        sys.stdout.flush()
        code = runner.run()
        print(f"log={runner.log_path}")
        with contextlib.suppress(Exception):
            text = Path(runner.log_path).read_text(errors="ignore")
            if "unsupported DTLS hook site" in text:
                print("NOTE: this process has a stale instrument from an earlier capture; "
                      "restart the game before capturing again.", file=sys.stderr)
        print(f"runner_exit={code}")
        print(f"game_alive={any(p.pid == attached for p in device.enumerate_processes())}")
        return 0
    finally:
        if device is not None:
            with contextlib.suppress(Exception):
                servers = [p.pid for p in device.enumerate_processes()
                           if p.name.lower() == "frida-server.exe"]
                if servers:
                    device.kill(servers[0])
        with contextlib.suppress(Exception):
            server.wait(timeout=10)
        capture_lock.release(lock)


if __name__ == "__main__":
    raise SystemExit(main())
