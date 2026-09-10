import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtempSync, writeFileSync, chmodSync, rmSync, existsSync, mkdirSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { once } from 'node:events';

const here = dirname(fileURLToPath(import.meta.url));
const temp = mkdtempSync(join(tmpdir(), 'shared-capture-'));
const fake = join(temp, 'python');
writeFileSync(fake, `#!/usr/bin/env python3
import json, os, pathlib, sys, time, runpy
if sys.argv[1].endswith('archive.py'):
    sys.argv = sys.argv[1:]
    runpy.run_path(sys.argv[0], run_name='__main__')
elif sys.argv[1].endswith('video.py'):
    import signal
    root = pathlib.Path(sys.argv[2])
    def stop(*_): (root / 'stop').touch()
    signal.signal(signal.SIGTERM, stop)
    (root / 'video-progress.txt').write_text('frame=30\\n')
    while not (root / 'stop').exists(): time.sleep(0.02)
    time.sleep(0.5)
    (root / 'gameplay.mkv').write_bytes(b'FAKE_VIDEO')
else:
    root = pathlib.Path(sys.argv[2])
    if (root.parent / 'fail').exists(): sys.exit(3)
    time.sleep(0.2)
    meta = root / 'captures/session/dtls'
    meta.mkdir(parents=True)
    (meta / 'keylog.txt').write_text('SECRET')
    (root / 'status.json').write_text(json.dumps(dict(bytes=42,count=2,errors=0)))
    while not (root / 'stop').exists(): time.sleep(0.02)
    time.sleep(0.3)
    (meta / 'meta.json').write_text(json.dumps(dict(started_at_utc='2026-01-01',stopped_at_utc='2026-01-01',ledger_bytes_received=42,ledger_batches_received=2,final_flush_acknowledged=True,sink_write_succeeded=True,secret='SECRET')))
`);
chmodSync(fake, 0o700);
const port = 18787;
const base = `http://127.0.0.1:${port}`;
const data = join(temp, 'data');
const managed = process.env.CAPTURE_TEST_YOUTUBE === '1';
const oauth = join(temp, 'oauth.json');
const keyFile = join(temp, 'stream.key');
const preload = join(temp, 'youtube-mock.mjs');
if (managed) {
  writeFileSync(oauth, JSON.stringify({ client_id: 'client', client_secret: 'secret', refresh_token: 'refresh', channel_id: 'channel', stream_id: 'stream' }), { mode: 0o600 });
  writeFileSync(keyFile, 'test-key', { mode: 0o600 });
  writeFileSync(preload, `import {appendFileSync} from 'node:fs';
  let broadcast;
  globalThis.fetch = async (input, options) => {
    const url = new URL(input);
    await new Promise(resolve=>setTimeout(resolve,30));
    if(url.hostname==='oauth2.googleapis.com') return Response.json({access_token:'access',expires_in:3600});
    const resource=url.pathname.split('/v3/')[1];
    if(resource==='channels') return Response.json({items:[{id:'channel'}]});
    if(resource==='liveStreams') return Response.json({items:[{snippet:{channelId:'channel'},cdn:{ingestionInfo:{streamName:'test-key'}}}]});
    if(resource==='liveBroadcasts/bind') {broadcast.contentDetails.boundStreamId='stream'; return Response.json(broadcast);}
    if(resource==='liveBroadcasts/transition') {
      appendFileSync(${JSON.stringify(join(temp, 'youtube-events'))}, JSON.stringify({action:'stop',name:broadcast.snippet.title})+'\\n');
      broadcast.status.lifeCycleStatus='complete'; return Response.json(broadcast);
    }
    if(options.method==='POST') {
      broadcast=JSON.parse(options.body); broadcast.id='12345678901'; broadcast.snippet.channelId='channel';broadcast.status.lifeCycleStatus='live';
      appendFileSync(${JSON.stringify(join(temp, 'youtube-events'))}, JSON.stringify({action:'start',name:broadcast.snippet.title})+'\\n');
      return Response.json(broadcast);
    }
    if(options.method==='DELETE') {
      appendFileSync(${JSON.stringify(join(temp, 'youtube-events'))}, JSON.stringify({action:'stop',name:broadcast.snippet.title})+'\\n');
      return new Response(null,{status:204});
    }
    return Response.json({items:[broadcast]});
  };`);
}
const server = spawn(process.execPath, [join(here, 'server.ts')], { env: { ...process.env, PORT: String(port), CAPTURE_DATA: data, CAPTURE_PYTHON: fake, ...(managed ? { CAPTURE_VIDEO: '1', YOUTUBE_OAUTH_CONFIG: oauth, YOUTUBE_KEY_FILE: keyFile, NODE_OPTIONS: `--import=${preload}` } : {}) }, stdio: ['ignore', 'pipe', 'inherit'] });
const state = async () => (await fetch(base + '/api/session')).json();
const action = (name: string) => fetch(base + '/api/' + name, { method: 'POST', headers: { Origin: base, 'X-Capture-Action': '1', 'Content-Type': 'application/json' }, body: name === 'start' ? JSON.stringify({ name: 'Test session à / safe' }) : undefined });
async function waitFor(predicate: () => Promise<boolean>) {
  const deadline = Date.now() + 5000;
  while (Date.now() < deadline) { if (await predicate()) return; await new Promise(r => setTimeout(r, 25)); }
  throw Error('Test deadline exceeded');
}
try {
  await once(server.stdout!, 'data');
  assert.equal((await fetch(base + '/api/start', { method: 'POST' })).status, 403);
  assert.equal((await fetch(base + '/api/start', { method: 'POST', headers: { Origin: 'http://evil.test', 'X-Capture-Action': '1' } })).status, 403);
  for (const name of ['', '   ', 'x'.repeat(101), 'bad\\nname'.replace('\\n', '\n'), '<bad>', 12]) {
    const invalid = await fetch(base + '/api/start', { method: 'POST', headers: { Origin: base, 'X-Capture-Action': '1' }, body: JSON.stringify({ name }) });
    assert.equal(invalid.status, 400);
  }
  const starts = await Promise.all(Array.from({ length: 8 }, () => action('start')));
  assert.equal(starts.filter(r => r.status === 202).length, 1);
  assert.equal(starts.filter(r => r.status === 409).length, 7);
  const id = (await state()).id;
  await waitFor(async () => (await state()).state === 'RUNNING');
  assert.equal((await state()).id, id);
  assert.equal((await state()).bytes, 42);
  await Promise.all([action('stop'), action('stop')]);
  assert.equal((await state()).state, 'STOPPING');
  assert.equal((await action('start')).status, 409);
  await waitFor(async () => (await state()).state === 'STOPPED');
  const stopped = await state();
  assert.equal(stopped.name, 'Test session à / safe');
  assert.ok(stopped.endedAt >= stopped.startedAt);
  const response = await fetch(base + stopped.download);
  assert.equal(response.status, 200);
  assert.equal(response.headers.get('content-disposition'), 'attachment; filename="Test-session-a-safe.zip"');
  const zip = join(temp, 'download.zip');
  writeFileSync(zip, Buffer.from(await response.arrayBuffer()));
  const check = spawn('python3', ['-c', "import zipfile,sys; z=zipfile.ZipFile(sys.argv[1]); assert z.testzip() is None; assert set(z.namelist()) <= {'metadata.json','youtube.txt'}; assert b'SECRET' not in z.read('metadata.json')", zip], { stdio: 'inherit' });
  assert.equal((await once(check, 'close'))[0], 0);
  for (const path of ['/download/../../owner', '/download/%2e%2e/owner', '/__proto__', '/constructor', '/logs/game-server.log', '/captures/keylog.txt']) assert.equal((await fetch(base + path)).status, 404);
  writeFileSync(join(data, 'fail'), '');
  await action('start'); await waitFor(async () => (await state()).state === 'ERROR');
  assert.ok((await state()).error); assert.equal((await state()).download, '');
  rmSync(join(data, 'fail'));
  await action('start'); // Stop during STARTING, then shut down the server.
  await action('stop'); server.kill('SIGTERM');
  assert.equal((await once(server, 'close'))[0], 0);
  assert.equal(existsSync(join(data, 'owner')), false);
  console.log('PASS: concurrent start/stop, startup cancellation, shared snapshot, child-exit gate, ZIP allowlist, traversal, origin, failure, SIGTERM cleanup');
} finally {
  if (server.exitCode === null) { server.kill('SIGTERM'); await once(server, 'close'); }
  if (managed) { const events = readFileSync(join(temp, 'youtube-events'), 'utf8').trim().split('\n').map(line => JSON.parse(line)); assert.equal(events.filter(e=>e.action==='start').length, events.filter(e=>e.action==='stop').length); assert.ok(events.every(e=>e.name==='Test session à / safe')); }
  rmSync(temp, { recursive: true, force: true });
}
