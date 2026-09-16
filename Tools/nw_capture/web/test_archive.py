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
            meta.with_name('keylog.txt').write_text('NEVER_EXPORT')
            # No ledger yet: nothing worth archiving.
            with self.assertRaises(ValueError):
                archive(root)
            self.assertFalse((root / 'capture.zip').exists())
            meta.with_name('ledger.bin').write_bytes(b'captured')
            # A game closed before STOP loses the final flush, not the ledger.
            archive(root)
            with zipfile.ZipFile(root / 'capture.zip') as output:
                self.assertIsNone(output.testzip())
                self.assertEqual(output.namelist(), ['metadata.json', 'ledger.bin'])
                self.assertIs(json.loads(output.read('metadata.json'))['final_flush_acknowledged'], False)
                self.assertNotIn(b'NEVER_EXPORT', output.read('metadata.json'))

    def test_failed_sink_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            meta = root / 'captures/session/dtls/meta.json'
            meta.parent.mkdir(parents=True)
            meta.write_text(json.dumps(dict(started_at_utc='start', stopped_at_utc='stop',
                ledger_bytes_received=8, ledger_batches_received=1,
                final_flush_acknowledged=True, sink_write_succeeded=False)))
            meta.with_name('ledger.bin').write_bytes(b'captured')
            with self.assertRaises(ValueError):
                archive(root)

    def test_session_title_and_video(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            meta = root / 'captures/session/dtls/meta.json'
            meta.parent.mkdir(parents=True)
            meta.write_text(json.dumps(dict(started_at_utc='start', stopped_at_utc='stop',
                ledger_bytes_received=12, ledger_batches_received=1,
                final_flush_acknowledged=True, sink_write_succeeded=True)))
            (root / 'session.json').write_text(json.dumps(dict(name='Session à', id='abc',
                streamKey='NEVER_EXPORT')))
            meta.with_name('ledger.bin').write_bytes(b'captured')
            meta.parent.parent.joinpath('fragments.jsonl').write_text('{"body":"deadbeef"}\n')
            (root / 'gameplay.mkv').write_bytes(b'LOCAL_VIDEO_ONLY')
            archive(root)
            with zipfile.ZipFile(root / 'capture.zip') as output:
                self.assertEqual(set(output.namelist()),
                                 {'metadata.json', 'ledger.bin', 'fragments.jsonl', 'gameplay.mkv'})
                self.assertEqual(output.read('fragments.jsonl'), b'{"body":"deadbeef"}\n')
                self.assertEqual(output.read('gameplay.mkv'), b'LOCAL_VIDEO_ONLY')
                self.assertEqual(json.loads(output.read('metadata.json'))['name'], 'Session à')
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
                self.assertEqual(output.read('ledger.bin'), b'raw')
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
