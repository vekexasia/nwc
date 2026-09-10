import json
import os
from unittest.mock import patch
from pathlib import Path
import tempfile
import unittest
import zipfile

from archive import archive


class ArchiveTests(unittest.TestCase):
    def test_allowlist_and_incomplete(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            meta = root / 'captures/session/dtls/meta.json'
            meta.parent.mkdir(parents=True)
            data = dict(started_at_utc='2026-01-01', stopped_at_utc='2026-01-01',
                        ledger_bytes_received=12, ledger_batches_received=1,
                        final_flush_acknowledged=False, sink_write_succeeded=True,
                        token='NEVER_EXPORT')
            meta.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                archive(root)
            self.assertFalse((root / 'capture.zip').exists())
            data['final_flush_acknowledged'] = True
            meta.write_text(json.dumps(data))
            meta.with_name('keylog.txt').write_text('NEVER_EXPORT')
            archive(root)
            with zipfile.ZipFile(root / 'capture.zip') as output:
                self.assertIsNone(output.testzip())
                self.assertEqual(output.namelist(), ['metadata.json'])
                self.assertNotIn(b'NEVER_EXPORT', output.read('metadata.json'))

    def test_session_title_and_youtube_link(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            meta = root / 'captures/session/dtls/meta.json'
            meta.parent.mkdir(parents=True)
            meta.write_text(json.dumps(dict(started_at_utc='start', stopped_at_utc='stop',
                ledger_bytes_received=12, ledger_batches_received=1,
                final_flush_acknowledged=True, sink_write_succeeded=True)))
            url = 'https://www.youtube.com/watch?v=12345678901'
            (root / 'session.json').write_text(json.dumps(dict(name='Session à', id='abc',
                youtubeUrl=url, streamKey='NEVER_EXPORT')))
            (root / 'gameplay.mkv').write_bytes(b'LOCAL_VIDEO_ONLY')
            archive(root)
            with zipfile.ZipFile(root / 'capture.zip') as output:
                self.assertEqual(set(output.namelist()), {'metadata.json', 'youtube.txt'})
                self.assertEqual(json.loads(output.read('metadata.json'))['name'], 'Session à')
                self.assertEqual(output.read('youtube.txt').decode().strip(), url)
                self.assertNotIn(b'NEVER_EXPORT', output.read('metadata.json'))

    def test_raw_export_is_explicit_and_excludes_keylog(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            meta = root / 'captures/session/dtls/meta.json'
            meta.parent.mkdir(parents=True)
            meta.write_text(json.dumps(dict(started_at_utc='start', stopped_at_utc='stop',
                ledger_bytes_received=3, ledger_batches_received=1,
                final_flush_acknowledged=True, sink_write_succeeded=True)))
            meta.with_name('ledger.bin').write_bytes(b'raw')
            meta.with_name('keylog.txt').write_text('TLS_SECRET')
            (root / 'stream.key').write_text('STREAM_SECRET')
            (root / 'gameplay.mkv').write_bytes(b'LOCAL_VIDEO_ONLY')
            with patch.dict(os.environ, {'CAPTURE_EXPORT_RAW': '1'}):
                archive(root)
            with zipfile.ZipFile(root / 'capture.zip') as output:
                self.assertEqual(output.read('captures/session/dtls/ledger.bin'), b'raw')
                self.assertNotIn('gameplay.mkv', output.namelist())
                self.assertFalse(any('keylog' in name or 'stream.key' in name for name in output.namelist()))

    def test_symlink_metadata_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            meta = root / 'captures/session/dtls/meta.json'
            meta.parent.mkdir(parents=True)
            secret = root / 'private.json'
            secret.write_text('{}')
            meta.symlink_to(secret)
            with self.assertRaises(ValueError):
                archive(root)


if __name__ == '__main__':
    unittest.main()
