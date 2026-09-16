import json
import os
from pathlib import Path
import resource
import runpy
import sys

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import nw_capture

output = Path(sys.argv[1]).resolve()
steam = sys.argv[2]
parent_pid = os.getppid()
if os.environ.get('CAPTURE_VIDEO', '1') != '0':
    resource.setrlimit(resource.RLIMIT_FSIZE, (2 * 1024 ** 3, 2 * 1024 ** 3))
os.umask(0o077)
import signal
signal.signal(signal.SIGTERM, lambda *_: (output / 'stop').touch())
signal.signal(signal.SIGINT, lambda *_: (output / 'stop').touch())


class ManagedRunner(nw_capture.HttpsTapRunner):
    def _wait_for_exit(self):
        self._web_ready = True
        while True:
            self.publish()
            if (output / 'stop').exists() or os.getppid() != parent_pid:
                return
            if self._detached.wait(0.5):
                self.exit_code = max(self.exit_code, 2)
                return

    def publish(self):
        with self._message_lock:
            value = {'bytes': self._ledger_bytes, 'count': self._ledger_batches,
                     'errors': self.exit_code, 'ready': True}
        temporary = output / 'status.tmp'
        temporary.write_text(json.dumps(value))
        temporary.replace(output / 'status.json')

    def _cleanup(self):
        super()._cleanup()
        if getattr(self, '_web_ready', False):
            self.publish()


# The launcher still owns Frida startup, flush/detach, extraction and cleanup.
nw_capture.HttpsTapRunner = ManagedRunner
sys.argv = [str(HERE / 'capture_proton.py'), '--steam-dir', steam,
            '--timeout', '0', '--output-dir', str(output)]
# Refuse an existing server before the launcher can mistake it for its child.
import socket
with socket.socket() as probe:
    probe.settimeout(0.5)
    if probe.connect_ex(('127.0.0.1', 27943)) == 0:
        raise SystemExit('Capture port already occupied')
runpy.run_path(str(HERE / 'capture_proton.py'), run_name='__main__')
