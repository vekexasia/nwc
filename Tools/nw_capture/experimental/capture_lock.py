"""Single-flight lock for the Frida captures.

Two captures at the same time leave the game process with a stale instrument: the second
attach fails with `unsupported DTLS hook site` and the process stays unusable until it is
restarted. This lock makes the second capture wait instead: it is an flock, so it is released
by the kernel when the holding process dies, and there is no stale-lock case to clean up.

    from capture_lock import acquire, release, owner

    handle = acquire("walktest")          # waits for a running capture
    try:
        ...
    finally:
        release(handle)
"""
from __future__ import annotations

import fcntl
import os
import time
from pathlib import Path

DEFAULT_PATH = Path(os.environ.get("NW_CAPTURE_LOCK", "/tmp/nw-capture.lock"))
DEFAULT_WAIT = float(os.environ.get("NW_CAPTURE_WAIT", "900"))


class CaptureBusy(RuntimeError):
    """Another capture held the lock for longer than the caller was willing to wait."""


def owner(path: Path = DEFAULT_PATH) -> str:
    """Who holds the lock, as written by the holder, or an empty string."""
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def acquire(label: str, path: Path = DEFAULT_PATH, wait: float | None = None):
    """Take the capture lock, waiting for a running capture, and return the open handle."""
    wait = DEFAULT_WAIT if wait is None else wait
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "a+")
    deadline = time.monotonic() + wait
    announced = False
    while True:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            if not announced:
                print(f"waiting: another capture is running ({owner(path) or 'unknown holder'})",
                      flush=True)
                announced = True
            if time.monotonic() > deadline:
                handle.close()
                raise CaptureBusy(f"another capture still holds {path}: {owner(path)}")
            time.sleep(2)
            continue
        handle.seek(0)
        handle.truncate()
        handle.write(f"pid={os.getpid()} label={label} since={time.strftime('%H:%M:%S')}")
        handle.flush()
        return handle


def release(handle) -> None:
    if handle is None:
        return
    try:
        handle.seek(0)
        handle.truncate()
        handle.flush()
        fcntl.flock(handle, fcntl.LOCK_UN)
    except Exception:
        pass
    try:
        handle.close()
    except Exception:
        pass
