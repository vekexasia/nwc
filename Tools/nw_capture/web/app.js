const element = id => document.getElementById(id);
let downloadedId = '';
let snapshot;
let observedAt = 0;
let pending = false;
function size(bytes) {
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let index = 0;
  while (bytes >= 1024 && index < units.length - 1) { bytes /= 1024; index += 1; }
  return `${index === 0 ? bytes : bytes.toFixed(1)} ${units[index]}`;
}
function render(value) {
  snapshot = value; observedAt = performance.now();
  for (const key of ['state', 'name', 'id', 'count', 'errors', 'error', 'videoState']) element(key).textContent = String(value[key]);
  for (const key of ['bytes', 'videoBytes']) element(key).textContent = size(value[key]);
  const labels = { steam: 'Steam running', game: 'New World running', python: 'Capture environment', frida: 'Frida server file', recorder: 'Video recorder', port: 'Capture port free' };
  element('ready').replaceChildren(...Object.entries(labels).map(([key, label]) => {
    const item = document.createElement('li');
    item.textContent = `${value.ready[key] ? 'OK' : 'MISSING'} - ${label}`;
    item.className = value.ready[key] ? 'ok' : 'missing';
    return item;
  }), Object.assign(document.createElement('li'), { textContent: `${value.ready.diskGB} GB free on the capture disk` }));
  const active = ['STARTING', 'RUNNING', 'STOPPING'].includes(value.state);
  element('session-name').disabled = active;
  element('start').disabled = pending || active;
  element('stop').disabled = pending || !active || value.state === 'STOPPING';
  element('download').hidden = !value.download;
  if (value.download) {
    element('download').href = value.download;
    if (downloadedId !== value.id) { downloadedId = value.id; element('download').click(); }
  }
}
async function poll() {
  try {
    const response = await fetch('/api/session', { signal: AbortSignal.timeout(3000) });
    if (!response.ok) throw Error('Server unavailable');
    render(await response.json()); element('connection').textContent = 'Connected to shared session';
  } catch {
    snapshot = null; element('connection').textContent = 'Disconnected. Capture may still be running; reconnecting...';
    element('start').disabled = element('stop').disabled = true;
  } finally { setTimeout(poll, 750); }
}
for (const action of ['start', 'stop']) element(action).onclick = async () => {
  pending = true; element('start').disabled = element('stop').disabled = true;
  try {
    const response = await fetch(`/api/${action}`, { method: 'POST', headers: { 'X-Capture-Action': '1', 'Content-Type': 'application/json' }, body: action === 'start' ? JSON.stringify({ name: element('session-name').value }) : undefined, signal: AbortSignal.timeout(5000) });
    if (!response.ok) { const data = await response.json(); element('error').textContent = data.error || 'Another client already changed this session.'; }
  } catch { element('error').textContent = 'Request uncertain; checking shared server state.'; }
  finally { pending = false; }
};
setInterval(() => {
  if (snapshot) {
    const now = snapshot.endedAt || snapshot.serverNow + performance.now() - observedAt;
    element('duration').textContent = `${snapshot.startedAt ? Math.max(0, (now - snapshot.startedAt) / 1000).toFixed(1) : 0}s`;
  }
}, 100);
poll();
