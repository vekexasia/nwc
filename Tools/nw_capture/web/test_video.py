import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest


class VideoTests(unittest.TestCase):
    def test_stop_signals_encoder_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = root / 'ffmpeg'
            fake.write_text('''#!/usr/bin/env python3
import signal,time,pathlib
count=0
def stop(*_):
    global count
    count+=1
signal.signal(signal.SIGINT,stop)
pathlib.Path('fake-ready').touch()
while count==0: time.sleep(.01)
time.sleep(.7)
pathlib.Path('signals').write_text(str(count))
raise SystemExit(255)
''')
            fake.chmod(0o700)
            env = dict(os.environ, PATH=directory + os.pathsep + os.environ['PATH'])
            env.pop('YOUTUBE_KEY_FILE', None)
            process = subprocess.Popen([sys.executable, str(Path(__file__).with_name('video.py')), directory, '5'], env=env)
            try:
                deadline = time.monotonic() + 3
                while not (root / 'fake-ready').exists():
                    if time.monotonic() >= deadline:
                        self.fail('Encoder did not start')
                    time.sleep(.01)
                process.send_signal(signal.SIGTERM)
                self.assertEqual(process.wait(timeout=5), 0)
                self.assertEqual((root / 'signals').read_text(), '1')
                self.assertEqual(json.loads((root / 'video-result.json').read_text())['exit'], 0)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()


if __name__ == '__main__':
    unittest.main()
