import contextlib, os, socket, subprocess, sys, time
from pathlib import Path
import frida

REPO = Path("~/git/personale/new-world-capture")
sys.path.insert(0, str(REPO / "Tools/nw_capture"))
from _runner import FridaRunner  # noqa: E402

TIMEOUT = float(sys.argv[1]) if len(sys.argv) > 1 else 60.0
STEAM = Path.home() / ".local/share/Steam/steamapps"
RUNTIME = str(STEAM / "common/SteamLinuxRuntime_4/run")
WINE = str(STEAM / "common/Proton 11.0/files/bin/wine")
PFX = str(STEAM / "compatdata/1063730/pfx")
PORT = 27943
name = time.strftime("proton_%Y%m%d_%H%M%S") + "-writetrace"
env = dict(os.environ, WINEPREFIX=PFX, WINEDEBUG="-all")

server = subprocess.Popen([RUNTIME, "--", WINE, str(REPO / "Tools/nw_capture/frida-server.exe"),
                           "--listen", f"127.0.0.1:{PORT}"], env=env,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
device = server_pid = None
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
    print("NewWorld PIDs:", [p.pid for p in targets], "server:", [p.pid for p in servers], flush=True)
    if len(targets) != 1 or len(servers) != 1:
        raise SystemExit("BLOCKED: expected exactly one NewWorld.exe and one frida-server.exe")
    server_pid = servers[0].pid
    runner = FridaRunner(None, scripts=["/tmp/nwc/probe_trace_writes.js"], timeout_s=TIMEOUT,
                         log_stem="trace_writes", session=name, host=f"127.0.0.1:{PORT}", pid=targets[0].pid)
    print("session:", runner.session, "ledger:", runner._ledger_path, flush=True)
    code = runner.run()
    print("runner exit:", code, "log:", runner.log_path, flush=True)
    print("game still running:", any(p.pid == targets[0].pid for p in device.enumerate_processes()), flush=True)
finally:
    if device is not None and server_pid is not None:
        with contextlib.suppress(Exception):
            device.kill(server_pid)
    with contextlib.suppress(Exception):
        server.wait(timeout=10)
