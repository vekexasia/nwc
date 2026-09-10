import { youtube, youtubeManaged } from './youtube.ts';
import http from 'node:http';
import { spawn, type ChildProcess } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync, existsSync, readdirSync, lstatSync, createReadStream } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
process.umask(0o077);
function integer(name: string, fallback: number, max: number) {
  const value = process.env[name] ?? String(fallback);
  if (!/^\d+$/.test(value) || Number(value) < 1 || Number(value) > max) throw Error(`Invalid ${name}`);
  return Number(value);
}
const port = integer('PORT', 8787, 65535);
const videoEnabled = process.env.CAPTURE_VIDEO === '1';
const youtubeUrl = process.env.YOUTUBE_WATCH_URL ?? '';
if (youtubeManaged && (!videoEnabled || !process.env.YOUTUBE_KEY_FILE)) throw Error('Managed YouTube requires video and stream key');
if (process.env.YOUTUBE_KEY_FILE && (!videoEnabled || (!youtubeManaged && !/^https:\/\/www\.youtube\.com\/watch\?v=[A-Za-z0-9_-]{11}$/.test(youtubeUrl)))) throw Error('YouTube requires video and a verified broadcast URL');
const seconds = integer('CAPTURE_SECONDS', 600, 3600);
const python = process.env.CAPTURE_PYTHON ?? resolve(here, '../../../.venv-capture/bin/python');
const steam = process.env.STEAM_DIR ?? join(process.env.HOME ?? '', '.local/share/Steam');
const root = resolve(process.env.CAPTURE_DATA ?? join(here, '../captures/web'));
mkdirSync(root, { recursive: true, mode: 0o700 });
// One server process only; refuse restart until operator checks any stale owner.
const lock = join(root, 'owner');
writeFileSync(lock, String(process.pid), { flag: 'wx', mode: 0o600 });
let child: ChildProcess | null = null;
let video: ChildProcess | null = null;
let collectorDone = false;
let finalizing = false;
let preparation: Promise<void> | null = null;
let collected = false;
let youtubeStatusPending = false;
let youtubeStatusAt = 0;
let closing = false;
let cleanupUncertain = false;
let stopAt = 0;
let session = { name: '', filename: '', youtubeUrl: '', youtubeState: youtubeManaged ? 'READY' : 'DISABLED', videoState: videoEnabled ? 'READY' : 'DISABLED', videoFrames: 0, id: '', state: 'IDLE', startedAt: 0, endedAt: 0, bytes: 0, count: 0, errors: 0, error: '', download: '' };
const active = () => ['STARTING', 'RUNNING', 'STOPPING'].includes(session.state);
const directory = () => join(root, session.id);
function stop() {
  if (!active()) return;
  if (session.state !== 'STOPPING') {
    session.state = 'STOPPING'; stopAt = Date.now();
    video?.kill('SIGTERM');
    try { writeFileSync(join(directory(), 'stop'), ''); }
    catch { fail('Cannot write stop request; cleanup watchdog active.'); }
  }
}
function fail(message: string) { session.error = message; session.errors = Math.max(1, session.errors); }
function size(path: string): number {
  let total = 0;
  const entries = readdirSync(path, { withFileTypes: true });
  if (entries.length > 10000) throw Error('File limit');
  for (const entry of entries) {
    const file = join(path, entry.name);
    if (entry.isSymbolicLink()) throw Error('Unsafe output');
    total += entry.isDirectory() ? size(file) : lstatSync(file).size;
  }
  return total;
}
function update() {
  if (!active()) return;
  try {
    const path = join(directory(), 'status.json');
    if (existsSync(path)) {
      if (lstatSync(path).size > 4096) throw Error('Invalid status');
      const data: unknown = JSON.parse(readFileSync(path, 'utf8'));
      if (!data || typeof data !== 'object' || !('bytes' in data) || !('count' in data) || !('errors' in data)) throw Error('Invalid status');
      for (const key of ['bytes', 'count', 'errors'] as const) {
        const value = data[key];
        if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0) throw Error('Invalid counters');
        session[key] = Math.max(session[key], value);
      }
      if (session.state === 'STARTING') session.state = 'RUNNING';
      if (data.errors && !session.error) fail('Collector reported errors; see private host logs.');
    }
    if (video && existsSync(join(directory(), 'video-progress.txt'))) {
      const progress = readFileSync(join(directory(), 'video-progress.txt'), 'utf8').slice(-4096);
      const frames = [...progress.matchAll(/^frame=(\d+)$/gm)];
      if (frames.length) { session.videoFrames = Number(frames.at(-1)![1]); if (session.videoFrames > 0 && session.videoState === 'STARTING') session.videoState = 'ENCODING'; }
    }
    if (size(directory()) > (videoEnabled ? 1024 : 256) * 1024 * 1024) { fail('Capture size limit reached.'); stop(); }
    if (Date.now() - session.startedAt > (seconds + (youtubeManaged ? 120 : 30)) * 1000) { fail('Capture deadline exceeded.'); stop(); }
    if (session.state === 'STARTING' && Date.now() - session.startedAt > (youtubeManaged ? 120000 : 30000)) { fail('Startup deadline exceeded.'); stop(); }
  } catch { fail('Capture monitoring failed; stop requested.'); stop(); }
  if (stopAt && Date.now() - stopAt > 30000 && (child?.pid || video?.pid)) {
    cleanupUncertain = true;
    fail('Cleanup deadline exceeded; capture incomplete. Check host before restarting.');
    try { for (const owned of [child, video]) if (owned?.pid) process.kill(-owned.pid, Date.now() - stopAt > 45000 ? 'SIGKILL' : 'SIGTERM'); }
    catch { fail('Unable to signal owned child; check host.'); }
  }
}
function saveSession() {
  writeFileSync(join(directory(), 'session.json'), JSON.stringify({ name: session.name, id: session.id, youtubeUrl: session.youtubeUrl, youtubeState: session.youtubeState, videoState: session.videoState, error: session.error }));
}
async function finish() {
  if (!collectorDone || video || preparation || finalizing) return;
  finalizing = true;
  session.state = 'STOPPING'; stopAt = Date.now();
  if (youtubeManaged) {
    session.youtubeState = 'ENDING';
    try {
      const result = await youtube('stop', session.id, session.name); session.youtubeState = result.state;
      if (result.state === 'CANCELLED') { session.youtubeUrl = ''; if (collected) fail('YouTube never went live; local video retained.'); }
    }
    catch (error) { console.error('YouTube closure failed:', error instanceof Error && error.name === 'Error' ? error.message : 'Network/response failure'); session.youtubeState = 'ERROR'; cleanupUncertain = true; fail('YouTube closure not confirmed; verify the owned broadcast before restarting.'); }
  }
  try { saveSession(); } catch { fail('Cannot save session metadata.'); session.state = 'ERROR'; session.endedAt = Date.now(); return; }
  if (!collected) { session.state = session.error ? 'ERROR' : 'STOPPED'; session.endedAt = Date.now(); return; }

  const archiver = spawn(python, [join(here, 'archive.py'), directory()], { detached: true, stdio: 'ignore' });
  child = archiver;
  archiver.on('error', () => fail('Archive process failed.'));
  archiver.on('close', (code) => {
    child = null; session.endedAt = Date.now();
    if (code === 0) {
      session.state = session.error ? 'ERROR' : 'STOPPED';
      session.download = `/download/${session.id}`;
    } else { session.state = 'ERROR'; fail('Capture incomplete or archive failed.'); }
  });
}
function launch(name: string) {
  if (closing || active()) return false;
  if (cleanupUncertain) throw Error('Operator cleanup required');
  if (readdirSync(root).length >= 11 || size(root) > 1024 * 1024 * 1024) throw Error('Private storage limit reached; operator must remove old captures.');
  const id = randomUUID();
  mkdirSync(join(root, id), { mode: 0o700 });
  const filename = name.normalize('NFKD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-zA-Z0-9_-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 100) || 'capture';
  session = { name, filename, youtubeUrl, youtubeState: youtubeManaged ? 'PREPARING' : 'DISABLED', videoState: videoEnabled ? 'STARTING' : 'DISABLED', videoFrames: 0, id, state: 'STARTING', startedAt: Date.now(), endedAt: 0, bytes: 0, count: 0, errors: 0, error: '', download: '' };
  try { saveSession(); } catch { session.state = 'ERROR'; session.endedAt = Date.now(); fail('Cannot save session metadata.'); throw Error('Session storage unavailable'); }
  stopAt = 0; collectorDone = false; finalizing = false; collected = false;
  if (youtubeManaged) {
    preparation = (async () => {
      try {
        const broadcast = await youtube('start', session.id, session.name);
        session.youtubeUrl = broadcast.url; session.youtubeState = broadcast.state; saveSession();
        if (session.state !== 'STOPPING') spawnCapture(); else collectorDone = true;
      } catch (error) {
        console.error('YouTube preparation failed:', error instanceof Error && error.name === 'Error' ? error.message : 'Network/response failure');
        fail('YouTube preparation failed. No gameplay transmitted.'); collectorDone = true; stop();
      }
    })();
    preparation.finally(() => { preparation = null; if (collectorDone) void finish(); });
  } else spawnCapture();
  return true;
}
function spawnCapture() {
  collected = true;
  if (videoEnabled) {
    video = spawn(python, [join(here, 'video.py'), directory(), String(seconds)], { detached: true, stdio: 'ignore' });
    video.on('error', () => { fail('Unable to start video encoder.'); stop(); });
    video.on('close', (code) => {
      update(); video = null;
      session.videoState = code === 0 ? 'STOPPED' : 'ERROR';
      if (code !== 0) fail('Video encoder failed; capture will be preserved if complete.');
      stop(); finish();
    });
  }
  child = spawn(python, [join(here, 'worker.py'), directory(), steam, String(seconds)], { detached: true, stdio: 'ignore' });
  child.on('error', () => fail('Unable to launch collector. Check Python/Steam configuration.'));
  child.on('close', (code, signal) => {
    update(); child = null; collectorDone = true;
    if (code !== 0 || signal) fail('Collector failed. Check game, Steam runtime and private host logs.');
    stop(); finish();
  });
}
const server = http.createServer(async (req, res) => {
  res.setHeader('Cache-Control', 'no-store');
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'");
  const host = req.headers.host;
  if (host !== `127.0.0.1:${port}` && host !== `localhost:${port}`) { res.writeHead(403).end(); return; }
  const reply = (code: number, body: unknown) => { res.writeHead(code, { 'Content-Type': 'application/json' }).end(JSON.stringify(body)); };
  if (req.method === 'POST') {
    if (req.headers.origin !== `http://${host}` || req.headers['x-capture-action'] !== '1' || req.headers['transfer-encoding'] || Number(req.headers['content-length'] ?? 0) > 1024) { reply(403, { error: 'Same-origin bounded action required.' }); return; }
    try {
      if (req.url === '/api/start') {
        let body = '';
        for await (const chunk of req) { body += chunk.toString(); if (Buffer.byteLength(body) > 1024) { reply(413, { error: 'Request too large.' }); return; } }
        let name;
        try { const data: unknown = JSON.parse(body); if (!data || typeof data !== 'object' || !('name' in data)) throw Error('Missing name'); name = data.name; } catch { reply(400, { error: 'Session name required.' }); return; }
        if (typeof name !== 'string' || !name.trim() || name.trim().length > 100 || /[\x00-\x1f\x7f<>]/.test(name)) { reply(400, { error: 'Use a session name of 1-100 characters without control characters or angle brackets.' }); return; }
        reply(launch(name.trim()) ? 202 : 409, { ...session, serverNow: Date.now() }); return; }
      if (req.url === '/api/stop') { stop(); reply(202, session); return; }
    } catch { reply(503, { error: 'Operation failed; check configuration or private storage limits.' }); return; }
  }
  if (req.method !== 'GET') { reply(405, {}); return; }
  if (req.url === '/api/session') { reply(200, { ...session, serverNow: Date.now() }); return; }
  const assets: Record<string, [string, string]> = { '/': ['index.html', 'text/html'], '/app.js': ['app.js', 'text/javascript'], '/style.css': ['style.css', 'text/css'] };
  const asset = Object.hasOwn(assets, req.url ?? '') ? assets[req.url ?? ''] : undefined;
  if (asset) { res.writeHead(200, { 'Content-Type': asset[1] }); res.end(readFileSync(join(here, asset[0]))); return; }
  if (session.download && req.url === session.download && ['STOPPED', 'ERROR'].includes(session.state)) {
    res.writeHead(200, { 'Content-Type': 'application/zip', 'Content-Disposition': `attachment; filename="${session.filename}.zip"` });
    const stream = createReadStream(join(directory(), 'capture.zip'));
    stream.on('error', () => res.destroy()); res.on('close', () => stream.destroy()); stream.pipe(res); return;
  }
  reply(404, {});
});
server.requestTimeout = 5000; server.headersTimeout = 5000; server.maxConnections = 32;
const timer = setInterval(() => {
  update();
  if (youtubeManaged && session.state === 'RUNNING' && !youtubeStatusPending && Date.now() - youtubeStatusAt > 10000) {
    youtubeStatusPending = true; youtubeStatusAt = Date.now(); const id = session.id;
    youtube('status', id, session.name).then(result => {
      if (session.id === id && session.state === 'RUNNING') session.youtubeState = result.state;
    }).catch(error => { console.error('YouTube status failed:', error instanceof Error && error.name === 'Error' ? error.message : 'Network/response failure'); if (session.id === id && session.state === 'RUNNING') { fail('YouTube status verification failed.'); stop(); } })
      .finally(() => { youtubeStatusPending = false; });
  }
  if (closing && !child && !video && !preparation && !active()) {
    clearInterval(timer);
    import('node:fs').then(({ unlinkSync }) => { if (!cleanupUncertain) unlinkSync(lock); server.close(); server.closeAllConnections(); }).catch(() => process.exitCode = 1);
  }
}, 500);
for (const signal of ['SIGINT', 'SIGTERM'] as const) process.on(signal, () => { closing = true; stop(); });
server.on('error', () => { closing = true; stop(); process.exitCode = 1; });
server.listen(port, '127.0.0.1', () => console.log(`Capture: http://127.0.0.1:${port}`));
