import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

os.umask(0o077)
root = Path(sys.argv[1])
parent = os.getppid()
stopping = False
encoder = None
signal_sent = False


def stop(*_):
    global stopping, signal_sent
    stopping = True
    # SIGINT tells the recorder to stop and finalize; repeating it aborts the file.
    if encoder is not None and encoder.poll() is None and not signal_sent:
        signal_sent = True
        encoder.send_signal(signal.SIGINT)


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)

code = 1
try:
    os.chdir(root)
    # gpu-screen-recorder works on both X11 and Wayland; ffmpeg x11grab recorded
    # black frames on Wayland sessions.
    target = os.environ.get('VIDEO_TARGET', 'screen')
    cmd = [os.environ.get('VIDEO_RECORDER', 'gpu-screen-recorder'),
           '-w', target,
           '-f', os.environ.get('VIDEO_FPS', '30'),
           '-a', os.environ.get('VIDEO_AUDIO_SOURCE', 'default_output'),
           '-bm', 'cbr', '-q', os.environ.get('VIDEO_BITRATE', '6000'),
           '-o', 'gameplay.mkv']
    # Wayland window capture goes through the portal; the operator picks the window
    # once and the saved token reuses that choice without a dialog.
    if target == 'portal':
        cmd[7:7] = ['-restore-portal-session', 'yes']
    with open('video.log', 'wb') as log:
        encoder = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log, stderr=log)
        (root / 'video-ready').touch()
        if stopping:
            stop()
        while encoder.poll() is None:
            if stopping or os.getppid() != parent:
                stop()
            time.sleep(0.1)
        code = encoder.wait(timeout=10)
except Exception:
    code = 1
finally:
    if encoder is not None and encoder.poll() is None:
        stop()
        try:
            encoder.wait(timeout=10)
        except subprocess.TimeoutExpired:
            encoder.kill()
            encoder.wait()
    (root / 'video-result.json').write_text(json.dumps({'exit': code}))
raise SystemExit(code)
