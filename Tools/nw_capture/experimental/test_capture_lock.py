"""Checks for the capture lock: a holder blocks a second acquire, and it frees on death."""
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import capture_lock  # noqa: E402

HOLDER = """
import fcntl, sys, time
handle = open(sys.argv[1], "a+")
fcntl.flock(handle, fcntl.LOCK_EX)
handle.seek(0); handle.truncate()
handle.write("pid=%d label=holder" % __import__("os").getpid()); handle.flush()
print("held", flush=True)
time.sleep(float(sys.argv[2]))
"""


class CaptureLockTest(unittest.TestCase):
    def test_second_acquire_waits_then_succeeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lock"
            holder = subprocess.Popen([sys.executable, "-c", HOLDER, str(path), "3"],
                                      stdout=subprocess.PIPE, text=True)
            self.assertEqual(holder.stdout.readline().strip(), "held")
            start = time.monotonic()
            try:
                try:
                    capture_lock.acquire("second", path=path, wait=0.5)
                    self.fail("acquire should have raised CaptureBusy while the holder runs")
                except capture_lock.CaptureBusy as busy:
                    self.assertIn("holder", str(busy))
                self.assertLess(time.monotonic() - start, 3.0)
                handle = capture_lock.acquire("second", path=path, wait=10)
                self.assertGreaterEqual(time.monotonic() - start, 2.0)   # it really waited
                self.assertIn("label=second", capture_lock.owner(path))
                capture_lock.release(handle)
                self.assertEqual(capture_lock.owner(path), "")
            finally:
                holder.wait(timeout=10)

    def test_free_lock_is_immediate(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lock"
            start = time.monotonic()
            handle = capture_lock.acquire("solo", path=path, wait=5)
            self.assertLess(time.monotonic() - start, 1.0)
            capture_lock.release(handle)


if __name__ == "__main__":
    unittest.main()
