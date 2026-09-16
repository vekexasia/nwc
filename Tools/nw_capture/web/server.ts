import http from 'node:http';
import { spawn, type ChildProcess } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync, existsSync, readdirSync, lstatSync, statSync, statfsSync, createReadStream } from 'node:fs';
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
const bind = process.env.CAPTURE_HOST || '127.0.0.1';
// A reverse proxy in front (Cloudflare Tunnel) sends its own hostname and an https origin.
const publicOrigin = process.env.CAPTURE_PUBLIC_ORIGIN || '';
const publicHost = publicOrigin ? new URL(publicOrigin).host : '';
const videoEnabled = process.env.CAPTURE_VIDEO !== '0';
// The gpu-screen-recorder backend writes one local file and cannot also push RTMPS.
if (process.env.YOUTUBE_KEY_FILE || process.env.YOUTUBE_OAUTH_CONFIG) throw Error('YouTube streaming was removed with the ffmpeg backend');
// Video needs room for its source file and the ZIP copy; capture-only mode is unlimited.
const storage = videoEnabled ? integer('CAPTURE_STORAGE_GB', 40, 512) * 1024 * 1024 * 1024 : 0;
const python = process.env.CAPTURE_PYTHON ?? resolve(here, '../../../.venv-capture/bin/python');
const steam = process.env.STEAM_DIR ?? join(process.env.HOME ?? '', '.local/share/Steam');
const root = resolve(process.env.CAPTURE_DATA ?? join(here, '../captures/web'));
mkdirSync(root, { recursive: true, mode: 0o700 });
// One server process only. A lock left by a dead server is cleared: worker.py still
// refuses to start while a previous Frida server holds port 27943.
const lock = join(root, 'owner');
try { writeFileSync(lock, String(process.pid), { flag: 'wx', mode: 0o600 }); }
catch {
  const owner = Number(readFileSync(lock, 'utf8').trim());
  let alive = true;
  try { process.kill(owner, 0); } catch (error) { alive = (error as NodeJS.ErrnoException).code !== 'ESRCH'; }
  if (!Number.isInteger(owner) || owner < 1) throw Error(`Unreadable lock ${lock}; check the host, then delete the file to take over`);
  if (alive) throw Error(`Capture server already running as PID ${owner}: open http://127.0.0.1:${port} to use it, or stop it with 'kill ${owner}' and wait for it to exit`);
  writeFileSync(lock, String(process.pid), { mode: 0o600 });
}
let child: ChildProcess | null = null;
let video: ChildProcess | null = null;
let collectorDone = false;
let finalizing = false;
let collected = false;
let closing = false;
let cleanupUncertain = false;
let stopAt = 0;
let session = { name: '', filename: '', videoState: videoEnabled ? 'READY' : 'DISABLED', videoBytes: 0, id: '', state: 'IDLE', startedAt: 0, endedAt: 0, bytes: 0, count: 0, errors: 0, error: '', download: '' };
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
function publicError(error: unknown) {
  if (error instanceof SyntaxError) return 'Invalid status JSON';
  if (!(error instanceof Error)) return 'Unknown error';
  const { code, syscall } = error as NodeJS.ErrnoException;
  return typeof code === 'string' ? `${code}${typeof syscall === 'string' ? ` during ${syscall}` : ''}` : error.message;
}
let preflight = { at: 0, value: {} };
function ready() {
  if (Date.now() - preflight.at < 2000) return preflight.value;
  const names = new Set<string>();
  for (const entry of readdirSync('/proc')) {
    if (!/^\d+$/.test(entry)) continue;
    try { names.add(readFileSync(`/proc/${entry}/comm`, 'utf8').trim()); } catch { /* process exited */ }
  }
  let collector = true;
  try { collector = !readFileSync('/proc/net/tcp', 'utf8').split('\n').slice(1).some((line) => { const columns = line.trim().split(/\s+/); return columns[1]?.endsWith(':6D27') && columns[3] === '0A'; }); } catch { /* no procfs */ }
  const recorder = process.env.VIDEO_RECORDER ?? (process.env.PATH ?? '').split(':').map((dir) => join(dir, 'gpu-screen-recorder')).find(existsSync) ?? '';
  const free = statfsSync(root);
  preflight = { at: Date.now(), value: {
    steam: names.has('steam'), game: names.has('NewWorld.exe'), python: existsSync(python),
    frida: existsSync(join(here, '../frida-server.exe')), recorder: !videoEnabled || existsSync(recorder),
    port: collector, diskGB: Math.floor(free.bavail * free.bsize / (1024 * 1024 * 1024)) } };
  return preflight.value;
}

function size(path: string): number {
  let total = 0;
  const entries = readdirSync(path, { withFileTypes: true });
  if (entries.length > 10000) throw Error('File limit');
  for (const entry of entries) {
    const file = join(path, entry.name);
    if (entry.isSymbolicLink()) throw Error('Unsafe output');
    try { total += entry.isDirectory() ? size(file) : lstatSync(file).size; }
    catch (error) {
      // The producer may rename a temporary file after readdir returned it.
      if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error;
    }
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
    if (video && existsSync(join(directory(), 'gameplay.mkv'))) {
      // The recorder reports no frame counter; growing file bytes show it is encoding.
      session.videoBytes = lstatSync(join(directory(), 'gameplay.mkv')).size;
      if (session.videoBytes > 0 && session.videoState === 'STARTING') session.videoState = 'ENCODING';
    }
    if (videoEnabled && size(directory()) > storage / 2) { fail('Capture size limit reached.'); stop(); }
  } catch (error) {
    console.error('Capture monitoring failed; requesting stop.', error);
    fail(`Capture monitoring failed: ${publicError(error)}; stop requested.`);
    stop();
  }
}
function saveSession() {
  writeFileSync(join(directory(), 'session.json'), JSON.stringify({ name: session.name, id: session.id, videoState: session.videoState, error: session.error }));
}
function finish() {
  if (!collectorDone || video || finalizing) return;
  finalizing = true;
  session.state = 'STOPPING'; stopAt = Date.now();
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
  if (videoEnabled && (readdirSync(root).length >= 11 || size(root) > storage)) throw Error('Private storage limit reached; operator must remove old captures.');
  const id = randomUUID();
  mkdirSync(join(root, id), { mode: 0o700 });
  const filename = name.normalize('NFKD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-zA-Z0-9_-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 100) || 'capture';
  session = { name, filename, videoState: videoEnabled ? 'STARTING' : 'DISABLED', videoBytes: 0, id, state: 'STARTING', startedAt: Date.now(), endedAt: 0, bytes: 0, count: 0, errors: 0, error: '', download: '' };
  try { saveSession(); } catch { session.state = 'ERROR'; session.endedAt = Date.now(); fail('Cannot save session metadata.'); throw Error('Session storage unavailable'); }
  stopAt = 0; collectorDone = false; finalizing = false; collected = false;
  spawnCapture();
  return true;
}
function spawnCapture() {
  collected = true;
  if (videoEnabled) {
    video = spawn(python, [join(here, 'video.py'), directory()], { detached: true, stdio: 'ignore' });
    video.on('error', () => { fail('Unable to start video encoder.'); stop(); });
    video.on('close', (code) => {
      update(); video = null;
      session.videoState = code === 0 ? 'STOPPED' : 'ERROR';
      if (code !== 0) fail('Video encoder failed; capture will be preserved if complete.');
      stop(); finish();
    });
  }
  child = spawn(python, [join(here, 'worker.py'), directory(), steam], { detached: true, stdio: 'ignore' });
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
  // Bound to a LAN address the Host may be any local IP; a name could be an attacker's, rebound to us.
  if (host !== `127.0.0.1:${port}` && host !== `localhost:${port}` && !(publicHost && host === publicHost) && !(bind !== '127.0.0.1' && new RegExp(`^\\d{1,3}(\\.\\d{1,3}){3}:${port}$`).test(host ?? ''))) { res.writeHead(403).end(); return; }
  const reply = (code: number, body: unknown) => { res.writeHead(code, { 'Content-Type': 'application/json' }).end(JSON.stringify(body)); };
  if (req.method === 'POST') {
    if ((req.headers.origin !== `http://${host}` && !(publicOrigin && req.headers.origin === publicOrigin)) || req.headers['x-capture-action'] !== '1' || req.headers['transfer-encoding'] || Number(req.headers['content-length'] ?? 0) > 1024) { reply(403, { error: 'Same-origin bounded action required.' }); return; }
    try {
      if (req.url === '/api/start') {
        let body = '';
        for await (const chunk of req) { body += chunk.toString(); if (Buffer.byteLength(body) > 1024) { reply(413, { error: 'Request too large.' }); return; } }
        let name;
        try { const data: unknown = JSON.parse(body); if (!data || typeof data !== 'object' || !('name' in data)) throw Error('Missing name'); name = data.name; } catch { reply(400, { error: 'Session name required.' }); return; }
        if (typeof name !== 'string' || !name.trim() || name.trim().length > 100 || /[\x00-\x1f\x7f<>]/.test(name)) { reply(400, { error: 'Use a session name of 1-100 characters without control characters or angle brackets.' }); return; }
        reply(launch(name.trim()) ? 202 : 409, { ...session, ready: ready(), serverNow: Date.now() }); return; }
      if (req.url === '/api/stop') { stop(); reply(202, session); return; }
    } catch { reply(503, { error: 'Operation failed; check configuration or private storage limits.' }); return; }
  }
  if (req.method !== 'GET') { reply(405, {}); return; }
  if (req.url === '/api/session') { reply(200, { ...session, ready: ready(), serverNow: Date.now() }); return; }
  const assets: Record<string, [string, string]> = { '/': ['index.html', 'text/html'], '/app.js': ['app.js', 'text/javascript'], '/style.css': ['style.css', 'text/css'] };
  const asset = Object.hasOwn(assets, req.url ?? '') ? assets[req.url ?? ''] : undefined;
  if (asset) { res.writeHead(200, { 'Content-Type': asset[1] }); res.end(readFileSync(join(here, asset[0]))); return; }
  if (session.download && req.url === session.download && ['STOPPED', 'ERROR'].includes(session.state)) {
    // Content-Length, so a download cut short is reported as failed instead of
    // landing as a short file that looks complete.
    const archive = join(directory(), 'capture.zip');
    res.writeHead(200, { 'Content-Type': 'application/zip', 'Content-Disposition': `attachment; filename="${session.filename}.zip"`, 'Content-Length': statSync(archive).size });
    const stream = createReadStream(archive);
    stream.on('error', () => res.destroy()); res.on('close', () => stream.destroy()); stream.pipe(res); return;
  }
  reply(404, {});
});
server.requestTimeout = 0; server.headersTimeout = 0; server.timeout = 0; server.keepAliveTimeout = 0; server.maxConnections = 32;
const timer = setInterval(() => {
  update();
  if (closing && !child && !video && !active()) {
    clearInterval(timer);
    import('node:fs').then(({ unlinkSync }) => { if (!cleanupUncertain) unlinkSync(lock); server.close(); server.closeAllConnections(); }).catch(() => process.exitCode = 1);
  }
}, 500);
for (const signal of ['SIGINT', 'SIGTERM'] as const) process.on(signal, () => { closing = true; stop(); });
server.on('error', (error) => { console.error(`Cannot serve on ${bind}:${port}: ${error.message}`); closing = true; stop(); process.exitCode = 1; });
server.listen(port, bind, () => console.log(`Capture: http://${bind === '0.0.0.0' ? '127.0.0.1' : bind}:${port}`));
