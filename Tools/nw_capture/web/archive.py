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
    if meta.get('final_flush_acknowledged') is not True or meta.get('sink_write_succeeded') is not True:
        raise ValueError('Incomplete capture')
    # Download intentionally excludes raw logs, HTTPS bodies/headers and TLS keys.
    # Only aggregate metadata is safe to expose without credential redaction.
    safe = {key: meta[key] for key in ('started_at_utc', 'stopped_at_utc',
            'ledger_bytes_received', 'ledger_batches_received',
            'final_flush_acknowledged', 'sink_write_succeeded')}
    session = json.loads((root / 'session.json').read_text()) if (root / 'session.json').exists() else {}
    safe.update({key: session[key] for key in ('name', 'id', 'youtubeUrl', 'youtubeState', 'videoState', 'error') if key in session})
    with zipfile.ZipFile(root / 'capture.zip', 'x', compression=zipfile.ZIP_DEFLATED) as output:
        output.writestr('metadata.json', json.dumps(safe, indent=2))
        if session.get('youtubeUrl'):
            output.writestr('youtube.txt', session['youtubeUrl'] + '\n')
        if os.environ.get('CAPTURE_EXPORT_RAW') == '1':
            for file in sorted((root / 'captures').rglob('*')):
                if file.is_symlink():
                    raise ValueError('Unsafe capture path')
                if file.is_file() and file.name != 'keylog.txt':
                    output.write(file, file.relative_to(root))



if __name__ == '__main__':
    archive(Path(sys.argv[1]))
