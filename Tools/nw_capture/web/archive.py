import json
import os
from pathlib import Path
import sys
import zipfile


def archive(root):
    metas = list((root / 'captures').glob('*/dtls/meta.json'))
    if len(metas) != 1 or metas[0].is_symlink():
        raise ValueError('Missing unique capture metadata')
    meta = json.loads(metas[0].read_text())
    ledger = metas[0].with_name('ledger.bin')
    if ledger.is_symlink() or not ledger.is_file() or ledger.stat().st_size == 0:
        raise ValueError('Missing capture ledger')
    if meta.get('sink_write_succeeded') is not True:
        raise ValueError('Incomplete capture')
    # A closed game ends the capture without the final flush: what already reached
    # the ledger stays valid, and final_flush_acknowledged records the difference.
    # The download carries the ledger, the video and aggregate metadata only.
    # Runtime logs, HTTPS bodies/headers and TLS keys stay on the host.
    safe = {key: meta[key] for key in ('started_at_utc', 'stopped_at_utc',
            'ledger_bytes_received', 'ledger_batches_received',
            'final_flush_acknowledged', 'sink_write_succeeded')}
    session = json.loads((root / 'session.json').read_text()) if (root / 'session.json').exists() else {}
    safe.update({key: session[key] for key in ('name', 'id', 'videoState', 'error') if key in session})
    with zipfile.ZipFile(root / 'capture.zip', 'x', compression=zipfile.ZIP_DEFLATED) as output:
        output.writestr('metadata.json', json.dumps(safe, indent=2))
        output.write(ledger, 'ledger.bin')
        video = root / 'gameplay.mkv'
        if video.is_file() and not video.is_symlink():
            # Stored: deflating an already compressed video only costs time.
            output.write(video, 'gameplay.mkv', compress_type=zipfile.ZIP_STORED)
        if os.environ.get('CAPTURE_EXPORT_RAW') == '1':
            for file in sorted((root / 'captures').rglob('*')):
                if file.is_symlink():
                    raise ValueError('Unsafe capture path')
                if file.is_file() and file.name != 'keylog.txt':
                    output.write(file, file.relative_to(root))



if __name__ == '__main__':
    archive(Path(sys.argv[1]))
