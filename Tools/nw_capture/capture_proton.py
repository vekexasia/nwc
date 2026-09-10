# /// script
# dependencies = ["frida==17.9.10"]
# ///
import argparse
import contextlib
import os
from pathlib import Path
import socket
import subprocess
import time

import frida
from nw_capture import HttpsTapRunner, run_extractor
from _runner import validate_mode

parser = argparse.ArgumentParser()
parser.add_argument('--launch', action='store_true', help='Launch through Steam and attach as soon as NewWorld.exe appears')
parser.add_argument('--steam-dir', type=Path, default=Path.home() / '.local/share/Steam', help='Steam installation containing steamapps')
parser.add_argument('--timeout', type=float, default=0, help='Capture seconds; 0 waits for Ctrl+C')
parser.add_argument('--output-dir', type=Path, help='Private output root (logs and captures); default beside script')
args = parser.parse_args()
try:
    validate_mode(None, '127.0.0.1:27943', 1, args.timeout)
except ValueError as error:
    parser.error(str(error))

os.umask(0o077)
root = Path(__file__).resolve().parent
steam = args.steam_dir.expanduser().resolve() / 'steamapps'
runtime = str(steam / 'common/SteamLinuxRuntime_4/run')
wine = str(steam / 'common/Proton 11.0/files/bin/wine')
env = dict(os.environ, WINEPREFIX=str(steam / 'compatdata/1063730/pfx'), WINEDEBUG='-all')
name = time.strftime('proton_%Y%m%d_%H%M%S')
output_root = args.output_dir.expanduser().resolve() if args.output_dir else root
if args.output_dir:
    import _runner
    import nw_capture
    _runner.LOGS_DIR = output_root / 'logs'
    _runner.CAPTURES_ROOT = nw_capture.CAPTURES_ROOT = output_root / 'captures'
logs = output_root / 'logs'
logs.mkdir(parents=True, exist_ok=True)
console = logs / (name + '-console.log')
if args.launch:
    if subprocess.run(['pgrep', '-x', 'NewWorld.exe'], stdout=subprocess.DEVNULL, check=False).returncode == 0:
        raise SystemExit('New World is already running; close it before --launch')
    with (logs / (name + '-steam.log')).open('w') as steam_output:
        steam_process = subprocess.Popen(['steam', '-applaunch', '1063730'], stdout=steam_output, stderr=subprocess.STDOUT, start_new_session=True)
    print('Steam launch requested; watching for NewWorld.exe', flush=True)
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        if subprocess.run(['pgrep', '-x', 'NewWorld.exe'], stdout=subprocess.DEVNULL, check=False).returncode == 0:
            steam_process.poll()
            print('NewWorld.exe detected; starting Frida immediately', flush=True)
            break
        time.sleep(0.05)
    else:
        raise SystemExit('NewWorld.exe did not appear within 120 seconds; capture not started')

server_pid = None
device = None
with (logs / 'game-server.log').open('w') as output:
    process = subprocess.Popen([runtime, '--', wine, str(root / 'frida-server.exe'), '--listen', '127.0.0.1:27943'], env=env, stdout=output, stderr=subprocess.STDOUT)
    try:
        for attempt in range(100):
            try:
                with socket.create_connection(('127.0.0.1', 27943), timeout=0.2):
                    break
            except OSError:
                if process.poll() is not None:
                    raise RuntimeError('server exited; see logs/game-server.log')
                time.sleep(0.2)
        else:
            raise RuntimeError('server not ready')
        device = frida.get_device_manager().add_remote_device('127.0.0.1:27943')
        processes = device.enumerate_processes()
        targets = [p for p in processes if p.name.lower() == 'newworld.exe']
        servers = [p for p in processes if p.name.lower() == 'frida-server.exe']
        if len(servers) == 1:
            server_pid = servers[0].pid
        print('Game Windows PIDs:', [p.pid for p in targets], flush=True)
        if len(targets) != 1 or server_pid is None:
            raise RuntimeError('Expected one running NewWorld.exe and one frida-server.exe')
        print('Capture log:', console, '; Ctrl+C stops capture, not the game', flush=True)
        # Keep Ctrl+C handling in the runner: flush/detach before stopping the server.
        with console.open('w') as capture_output, contextlib.redirect_stdout(capture_output), contextlib.redirect_stderr(capture_output):
            runner = HttpsTapRunner(None, args.timeout, name, '127.0.0.1:27943', targets[0].pid)
            result = runner.run()
        extracted = run_extractor(runner.log_path, name, False)
        result = result or extracted
        print('Capture exit:', result, 'console:', console, flush=True)
        print('Same game still enumerated:', any(p.pid == targets[0].pid for p in device.enumerate_processes()), flush=True)
    finally:
        try:
            if device is not None and server_pid is not None:
                try:
                    device.kill(server_pid)
                except (frida.TransportError, frida.ServerNotRunningError) as error:
                    print('Server cleanup:', error, flush=True)
        finally:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=5)
raise SystemExit(result)
