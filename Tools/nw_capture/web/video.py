import ctypes as C
from ctypes.util import find_library
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

os.umask(0o077)
root = Path(sys.argv[1])
seconds = int(sys.argv[2])
parent = os.getppid()
stopping = False
encoder = None
signal_sent = False
started = time.monotonic()
stop_started = 0.0


def stop(*_):
    global stopping, signal_sent, stop_started
    if not stopping:
        stop_started = time.monotonic()
    stopping = True
    if encoder is not None and encoder.poll() is None and not signal_sent:
        signal_sent = True
        encoder.send_signal(signal.SIGINT)


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
interrupt_type = C.CFUNCTYPE(C.c_int, C.c_void_p)


@interrupt_type
def interrupted(_):
    return int((stopping and time.monotonic() - stop_started > 5) or os.getppid() != parent or time.monotonic() - started > seconds + 30)


class Interrupt(C.Structure):
    _fields_ = [('callback', interrupt_type), ('opaque', C.c_void_p)]


context = C.c_void_p()
av = None
code = 1
sent = 0
try:
    key_file = os.environ.get('YOUTUBE_KEY_FILE')
    if key_file:
        key_path = Path(key_file)
        if key_path.stat().st_mode & 0o077:
            raise ValueError('Stream key file must be private')
        key = key_path.read_text().strip()
        if not key or len(key) > 256 or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in key):
            raise ValueError('Invalid stream key')
        av = C.CDLL(find_library('avformat'))
        util = C.CDLL(find_library('avutil'))
        util.av_log_set_level(-8)
        av.avio_open2.argtypes = [C.POINTER(C.c_void_p), C.c_char_p, C.c_int, C.POINTER(Interrupt), C.c_void_p]
        av.avio_write.argtypes = [C.c_void_p, C.c_void_p, C.c_int]
        av.avio_flush.argtypes = [C.c_void_p]
        av.avio_closep.argtypes = [C.POINTER(C.c_void_p)]
        interrupt = Interrupt(interrupted, None)
        if av.avio_open2(C.byref(context), ('rtmps://a.rtmps.youtube.com:443/live2/' + key).encode(), 2, C.byref(interrupt), None) < 0:
            raise RuntimeError('YouTube connection failed')
        del key
    os.chdir(root)
    cmd = ['ffmpeg', '-hide_banner', '-nostdin', '-loglevel', 'warning', '-stats_period', '1',
           '-progress', 'video-progress.txt', '-thread_queue_size', '512', '-f', 'x11grab',
           '-video_size', os.environ.get('VIDEO_SIZE', '1920x1080'), '-framerate', '30',
           '-i', os.environ.get('DISPLAY', ':0'), '-thread_queue_size', '512', '-f', 'pulse',
           '-i', os.environ.get('VIDEO_AUDIO_SOURCE', 'default'), '-t', str(seconds),
           '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'h264_nvenc', '-preset', 'p4', '-tune', 'll',
           '-b:v', '6M', '-maxrate', '6M', '-bufsize', '12M', '-g', '60', '-pix_fmt', 'yuv420p',
           '-c:a', 'aac', '-b:a', '160k', '-ar', '48000', '-ac', '2', '-flags', '+global_header']
    cmd += ['-f', 'tee', '[f=flv:flvflags=no_duration_filesize]pipe:1|[f=matroska]gameplay.mkv'] if av else ['-f', 'matroska', 'gameplay.mkv']
    with open('video.log', 'wb') as log:
        encoder = subprocess.Popen(cmd, stdout=subprocess.PIPE if av else subprocess.DEVNULL, stderr=log)
        (root / 'video-ready').touch()
        if stopping:
            stop()
        if av:
            while data := encoder.stdout.read(65536):
                av.avio_write(context, data, len(data))
                av.avio_flush(context)
                sent += len(data)
                if stopping or interrupted(None):
                    stop()
        else:
            while encoder.poll() is None:
                if stopping or interrupted(None):
                    stop()
                time.sleep(0.1)
        code = encoder.wait(timeout=10)
        # FFmpeg exits 255 after an intentional SIGINT, flushing its trailer.
        if stopping and code == 255:
            code = 0
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
    if av and context:
        if av.avio_closep(C.byref(context)) < 0:
            code = 1
    (root / 'video-result.json').write_text(json.dumps({'exit': code, 'bytesSent': sent, 'rtmps': bool(av)}))
raise SystemExit(code)
