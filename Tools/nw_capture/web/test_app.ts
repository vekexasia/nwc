import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createContext, runInContext } from 'node:vm';

// A reload gives app.js a fresh scope but the same sessionStorage, which is the
// whole point of keeping the downloaded id there: the archive downloads once.
const source = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'app.js'), 'utf8');
const store = new Map<string, string>();
const session = { name: 'run', filename: 'run', videoState: 'DISABLED', videoBytes: 0, id: 'abc-123', state: 'STOPPED', startedAt: 1, endedAt: 2, bytes: 1, count: 1, errors: 0, error: '', download: '/download/abc-123', ready: { steam: true, game: true, python: true, frida: true, recorder: true, port: true, diskGB: 800 }, serverNow: 3 };

function load() {
  let clicks = 0;
  const node = () => ({ textContent: '', className: '', hidden: false, href: '', value: '', disabled: false, onclick: null, click: () => { clicks += 1; }, replaceChildren: () => {}, appendChild: () => {} });
  const context = createContext({
    document: { getElementById: node, createElement: node },
    sessionStorage: { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v) },
    performance: { now: () => 0 },
    fetch: async () => { throw Error('offline'); },
    setTimeout: () => 0, setInterval: () => 0,
    Object, String, Math, Error, JSON,
  });
  runInContext(source, context);
  runInContext('render(session)', Object.assign(context, { session }));
  return clicks;
}

assert.equal(load(), 1, 'first load downloads the archive');
assert.equal(load(), 0, 'a reload must not download it again');
store.clear();
assert.equal(load(), 1, 'a new tab downloads again');
console.log('PASS: archive downloads once per session id, not once per page load');
