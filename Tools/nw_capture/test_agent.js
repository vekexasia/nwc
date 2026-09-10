// Mock-only checks: node Tools/nw_capture/test_agent.js [ledger.bin events.jsonl]
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = ['_common.js', '_dtls_ledger.js', 'nw_https_tap.js']
    .map(n => fs.readFileSync(path.join(__dirname, n), 'utf8')).join('\n');
// Sanitized upstream hook fixture: image size and instruction fingerprints only.
// Source: Aeternum-World logs/20260611-024200_nw_https_tap.log, first two events.
const evidence = [
  {
    "size": 183214080
  },
  {
    "first16_ssl_read": "B8 38 00 00 00 E8 C6 50 1B 00 48 2B E0 45 85 C0",
    "first16_ssl_write": "B8 38 00 00 00 E8 86 4A 1B 00 48 2B E0 45 85 C0",
    "first16_nss_keylog": "40 57 41 55 41 56 41 57 B8 48 00 00 00 E8 FE 44"
  }
];
const base = 0x140000000n;
const sites = [0x1478f17e0n, 0x1478f1e20n, 0x1478f23a0n];

function fixture(options = {}) {
    const hooks = new Map(), events = [], binary = [], order = [];
    const memory = new Map();
    ['first16_ssl_read', 'first16_ssl_write', 'first16_nss_keylog'].forEach((key, i) => {
        memory.set(sites[i], Uint8Array.from(evidence[1][key].split(' ').map(s => parseInt(s, 16))));
    });
    if (options.badSite !== undefined) memory.get(sites[options.badSite])[0] ^= 1;
    class Pointer {
        constructor(n) { this.n = BigInt(n instanceof Pointer ? n.n : n); }
        add(n) { return new Pointer(this.n + new Pointer(n).n); }
        sub(n) { return new Pointer(this.n - new Pointer(n).n); }
        compare(p) { return this.n < p.n ? -1 : this.n > p.n ? 1 : 0; }
        equals(p) { return this.n === p.n; }
        isNull() { return this.n === 0n; }
        toString() { return '0x' + this.n.toString(16); }
        toInt32() { return Number(BigInt.asIntN(32, this.n)); }
        toUInt32() { return Number(BigInt.asUintN(32, this.n)); }
        readU16() {
            return new Map([[base, options.badMZ ? 0 : 0x5a4d], [base + 0x84n, 0x8664],
                [base + 0x98n, 0x20b]]).get(this.n) || 0;
        }
        readU32() {
            return new Map([[base + 0x3cn, 0x80], [base + 0x80n, 0x4550],
                [base + 0xd0n, evidence[0].size]]).get(this.n) || 0;
        }
        readByteArray(n) { return memory.get(this.n).slice(0, n).buffer; }
        readUtf8String(n) { return Buffer.from(memory.get(this.n)).subarray(0, n).toString(); }
    }
    const ptr = n => new Pointer(n);
    const mod = {name: 'NewWorld.exe', base: ptr(base), size: evidence[0].size};
    const sandbox = {
        ptr, rpc: {exports: {}},
        Process: {
            platform: options.platform || 'windows', arch: options.arch || 'x64',
            pointerSize: options.pointerSize || 8, getCurrentThreadId: () => 7,
            findModuleByName: name => name === 'NewWorld.exe' ? mod : null,
            findRangeByAddress: () => ({base: ptr(base), size: mod.size,
                protection: options.nonExecutable ? 'r--' : 'r-x'}),
        },
        Interceptor: {
            attach(addr, callbacks) { hooks.set(addr.toString(), callbacks); return {detach() {}}; },
            detachAll() { order.push('detach-producers'); },
        },
        setInterval: () => 1,
        clearInterval: () => order.push('clear-timer'),
        send(event, data) {
            events.push(event);
            if (data) { binary.push(Buffer.from(data)); order.push('ledger'); }
            if (event.type === 'capture_stopped') order.push('ack');
        },
    };
    const context = vm.createContext(sandbox);
    return {hooks, events, binary, order, memory, ptr, context,
        load: () => vm.runInContext(source, context),
        eval: code => vm.runInContext(code, context)};
}

for (const options of [{platform: 'linux'}, {arch: 'ia32'}, {pointerSize: 4},
    {badMZ: true}, {nonExecutable: true}, {badSite: 0}, {badSite: 1}, {badSite: 2}]) {
    const f = fixture(options);
    assert.throws(f.load);
    assert.equal(f.hooks.size, 0, 'validation must precede ALL interception');
}
const f = fixture();
f.load();
assert.equal(f.hooks.size, 3);
f.eval("MOD_WINHTTP = {findExportByName: () => ptr('0x140001000')}; hookWinHttpSetStatusCallback();");
const setCallback = f.hooks.get('0x140001000');
const cb = f.ptr(0x140002000n);
for (const handle of [1, 2]) {
    f.eval(`requestMap.set('${f.ptr(handle)}', {host: 'example.test', path: '/', respBody: []});
        nwSend('http_request', {h: '${f.ptr(handle)}', host: 'example.test', path: '/', verb: 'GET'});`);
    const args = [f.ptr(handle), cb, f.ptr(0xffffffff), f.ptr(0)];
    setCallback.onEnter(args);
    assert.equal(args[1], cb, 'registration pointer must remain application-owned');
}
assert.equal(f.hooks.size, 5, 'shared callback observed once');
assert.equal(setCallback.onLeave, undefined, 'registration return value stays untouched');
for (const value of [0, -1]) setCallback.onEnter([f.ptr(1), f.ptr(value), f.ptr(0), f.ptr(0)]);
assert.equal(f.hooks.size, 5);
f.memory.set(0x140003000n, Buffer.from('hello'));
const callback = f.hooks.get(cb.toString());
for (const handle of [1, 2]) callback.onEnter([f.ptr(handle), f.ptr(99), f.ptr(0x80000), f.ptr(0x140003000n), f.ptr(5)]);
assert.equal(f.events.filter(e => e.type === 'http_response_body_chunk').length, 2);
assert.equal(callback.onLeave, undefined, 'native callback execution is not replaced');
assert(!source.includes('new NativeCallback'));
assert(!source.includes('new NativeFunction'));

// One uncompressed carrier message: first sequence present, rel-sequence omitted.
f.memory.set(0x140004000n, Uint8Array.from([0x80, 1, 0, 1, 0x18, 0, 2, 0, 1, 104, 105]));
const sslRead = f.hooks.get('0x1478f17e0');
const call = {};
sslRead.onEnter.call(call, [f.ptr(42), f.ptr(0x140004000n)]);
sslRead.onLeave.call(call, f.ptr(11));
assert.equal(f.binary.length, 0, 'record must be pending before stop');
f.eval('rpc.exports.stop()');
assert.deepEqual(f.order, ['detach-producers', 'clear-timer', 'ledger', 'ack']);
assert.equal(f.binary.length, 1);
const count = f.events.length;
sslRead.onLeave.call(call, f.ptr(11));
callback.onEnter([f.ptr(1), f.ptr(0), f.ptr(0x80000), f.ptr(0x140003000n), f.ptr(5)]);
assert.equal(f.events.length, count, 'in-flight callbacks suppressed after stop');
const stats = f.events.at(-1).dtls;
assert.equal(stats.bytes, f.binary[0].length);
assert.equal(stats.flushes, 1);
if (process.argv[2]) fs.writeFileSync(process.argv[2], Buffer.concat(f.binary));
if (process.argv[3]) fs.writeFileSync(process.argv[3], f.events.map(e => JSON.stringify(e)).join('\n'));
console.log('Agent validation, callback observation, final flush and late-callback guards passed.');
