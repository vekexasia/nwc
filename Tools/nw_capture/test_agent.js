// Mock-only checks: node Tools/nw_capture/test_agent.js [ledger.bin events.jsonl]
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = ['_common.js', '_dtls_ledger.js', 'nw_https_tap.js', 'experimental/nw_join_probe.js']
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

// One uncompressed carrier message: first sequence present, rel-sequence present.
f.memory.set(0x140004000n, Uint8Array.from([0x80, 1, 0, 1, 0x08, 0, 2, 0, 1, 0, 0, 104, 105]));
const sslRead = f.hooks.get('0x1478f17e0');
const call = {};
sslRead.onEnter.call(call, [f.ptr(42), f.ptr(0x140004000n)]);
sslRead.onLeave.call(call, f.ptr(13));
assert.equal(f.binary.length, 0, 'record must be pending before stop');
f.eval('rpc.exports.stop()');
assert.deepEqual(f.order, ['detach-producers', 'clear-timer', 'ledger', 'ack']);
assert.equal(f.binary.length, 1);
const count = f.events.length;
sslRead.onLeave.call(call, f.ptr(13));
callback.onEnter([f.ptr(1), f.ptr(0), f.ptr(0x80000), f.ptr(0x140003000n), f.ptr(5)]);
assert.equal(f.events.length, count, 'in-flight callbacks suppressed after stop');
const stats = f.events.at(-1).dtls;
assert.equal(stats.bytes, f.binary[0].length);
assert.equal(stats.flushes, 1);
if (process.argv[2]) fs.writeFileSync(process.argv[2], Buffer.concat(f.binary));
if (process.argv[3]) fs.writeFileSync(process.argv[3], f.events.map(e => JSON.stringify(e)).join('\n'));

function checkFragmentCapture() {
    const source = fs.readFileSync(path.join(__dirname, 'experimental/nw_join_probe.js'), 'utf8');
    const imageBase = 0x140000000n;
    const hooks = new Map(), events = [], pointers = new Map(), byteRanges = [];
    let cursor, baseInstalls = 0, baseStops = 0;

    class Pointer {
        constructor(n) { this.n = BigInt(n instanceof Pointer ? n.n : n); }
        add(n) { return new Pointer(this.n + new Pointer(n).n); }
        sub(n) { return new Pointer(this.n - new Pointer(n).n); }
        compare(p) { return this.n < p.n ? -1 : this.n > p.n ? 1 : 0; }
        toString() { return '0x' + this.n.toString(16); }
        toInt32() { return Number(BigInt.asIntN(32, this.n)); }
        toUInt32() { return Number(BigInt.asUintN(32, this.n)); }
        readPointer() {
            if (this.n === 0x4010n) return cursor;
            const value = pointers.get(this.n);
            if (value === undefined) throw new Error('unmapped pointer ' + this);
            return new Pointer(value);
        }
        readU16() {
            if (this.n !== 0x2000n) throw new Error('unmapped u16 ' + this);
            return 41;
        }
        readByteArray(length) {
            for (const [start, bytes] of byteRanges) {
                const offset = Number(this.n - start);
                if (offset >= 0 && offset + length <= bytes.length) {
                    return bytes.slice(offset, offset + length).buffer;
                }
            }
            throw new Error('unmapped bytes ' + this);
        }
    }

    const ptr = value => new Pointer(value);
    const module = {name: 'NewWorld.exe', base: ptr(imageBase), size: 183214080};
    const before = ptr(0x5000);
    const body = new Uint8Array(2 + 8193);
    body[0] = 7;
    body[1] = 100;
    for (let i = 2; i < body.length; i++) body[i] = i & 0xff;
    byteRanges.push([before.n, body]);
    pointers.set(0x3000n, 0x4000n);              // args[0] -> reader context
    pointers.set(0x6008n, 0x7000n);              // vector end
    pointers.set(0x6ff0n, 0x8000n);              // final vector entry -> object
    pointers.set(0x8000n, imageBase + 0x8480a70n); // object -> vtable
    pointers.set(imageBase + 0x8480a70n + 0x90n, imageBase + 0x5dd9cf0n);

    const sandbox = {
        rpc: {exports: {
            install() { baseInstalls++; },
            stop() { baseStops++; },
        }},
        Process: {
            findModuleByName: name => name === 'NewWorld.exe' ? module : null,
            enumerateModules: () => [module],
        },
        Interceptor: {
            attach(address, callbacks) { hooks.set(address.toString(), callbacks); return {detach() {}}; },
        },
        setInterval: () => 1,
        clearInterval: () => {},
        send(event) { events.push(JSON.parse(JSON.stringify(event))); },
    };
    const context = vm.createContext(sandbox);
    vm.runInContext(source, context);
    context.rpc.exports.install();
    assert.equal(baseInstalls, 1, 'probe install must preserve earlier capture hooks');

    const record = hooks.get(ptr(imageBase + 0x6af20d0n).toString());
    const chunk = hooks.get(ptr(imageBase + 0x6af2340n).toString());
    const recordCall = {threadId: 9};
    record.onEnter.call(recordCall, [ptr(0), ptr(0x2000)]);
    function capture(payloadLength, accepted = true) {
        cursor = before;
        const call = {threadId: 9};
        chunk.onEnter.call(call, [ptr(0x3000), ptr(0x6000)]);
        cursor = before.add(2 + payloadLength);
        chunk.onLeave.call(call, ptr(accepted ? 1 : 0));
    }
    for (let i = 0; i < 20; i++) capture(8192);
    capture(8193);
    capture(4, false);
    body[1] = 0;
    capture(16 + 4);
    context.rpc.exports.stop();

    const join = events.find(event => event.type === 'join_samples');
    assert.equal(join.items.length, 22);
    assert.equal(join.items[0].length, 7, 'join_samples tuple shape changed');
    assert.equal(join.items[0][5], 8192);
    assert.equal(join.items[0][6].length, 400, 'join_samples must retain the 200-byte view');

    const batches = events.filter(event => event.type === 'fragment_samples');
    assert(batches.length >= 2, 'fragment stream must flush by encoded bytes');
    assert(batches.every(batch => batch.encoded_bytes <= 256 * 1024));
    const fragments = batches.flatMap(batch => batch.items);
    assert.equal(fragments.length, 21);
    assert.deepEqual(Object.keys(fragments[0]),
        ['key', 'v1', 'v2', 'type', 'class', 'decoder', 'accepted', 'body']);
    assert.equal(fragments[0].key, 7);
    assert.equal(fragments[0].class, 0x8480a70);
    assert.equal(fragments[0].decoder, 0x5dd9cf0);
    assert.equal(fragments[0].body.length, 8192 * 2);
    const inlineUuid = fragments.at(-1);
    assert.equal(inlineUuid.type, 0);
    assert.equal(inlineUuid.body, Buffer.from(body.slice(18, 22)).toString('hex'),
        'inline type UUID must not be part of the decoder body');
    const stats = events.find(event => event.type === 'fragment_stats');
    assert.equal(stats.oversized, 1);
    assert.equal(stats.captured, 21);
    assert.equal(stats.sent, 21);
    assert.equal(stats.batches, batches.length);
    assert.equal(stats.dropped, 0);
    assert.equal(stats.refused, 1);
    assert.equal(baseStops, 1, 'probe stop must finish the shared capture lifecycle');
}
checkFragmentCapture();
console.log('Agent validation, callback observation, fragment bounds and final flush passed.');
