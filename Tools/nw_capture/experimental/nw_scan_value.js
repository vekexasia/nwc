// nw_scan_value.js - find the live copy of a numeric value (health, mana, ...) in game memory
// and watch it change. Read-only: Memory.scan + Memory.read*, nothing is written.
//
// args:  values (comma separated, e.g. "10520"), scan_mb (default 900), watch_seconds (default 120)

const args = typeof scriptArgs !== "undefined" && scriptArgs.length ? scriptArgs : [];
const VALUES = (args[0] || "10520").split(",").map(function (s) { return Number(s); });
const SCAN_MB = Number(args[1] || 900);
const WATCH_S = Number(args[2] || 120);

function patternsFor(v) {
    const out = [];
    const u32 = new Uint8Array(new Uint32Array([v >>> 0]).buffer);
    const i32 = new Uint8Array(new Int32Array([v | 0]).buffer);
    const f32 = new Uint8Array(new Float32Array([v]).buffer);
    function hex(a) { return Array.from(a).map(function (b) { return (b < 16 ? "0" : "") + b.toString(16); }).join(" "); }
    out.push({ kind: "u32le", hex: hex(u32) });
    out.push({ kind: "u32be", hex: hex(Array.from(u32).reverse()) });
    out.push({ kind: "f32le", hex: hex(f32) });
    out.push({ kind: "f32be", hex: hex(Array.from(f32).reverse()) });
    if (v >= 0 && v <= 0xffff) {
        const u16 = new Uint8Array(new Uint16Array([v]).buffer);
        out.push({ kind: "u16le", hex: hex(u16) });
        out.push({ kind: "u16be", hex: hex(Array.from(u16).reverse()) });
    }
    return out;
}

const candidates = [];
let watchTimer = null;
let installed = false;

function scanValue(pattern) {
    let scanned = 0;
    const limit = SCAN_MB * 1024 * 1024;
    const ranges = Process.enumerateRanges({ protection: "rw-", coalesce: true });
    for (const range of ranges) {
        if (scanned >= limit) break;
        scanned += range.size;
        try {
            Memory.scanSync(range.base, range.size, pattern.hex.replace(/ /g, "")).forEach(function (m) {
                candidates.push({ address: m.address, kind: pattern.kind, value: pattern.value });
            });
        } catch (e) { /* unreadable range, keep going */ }
    }
    return scanned;
}

function main() {
    const report = { values: VALUES, hits: {} };
    for (const v of VALUES) {
        for (const pattern of patternsFor(v)) {
            pattern.value = v;
            const scanned = scanValue(pattern);
            report.scanned_mb = Math.round(scanned / 1024 / 1024);
        }
    }
    report.hits = candidates.map(function (c) { return { address: c.address.toString(), kind: c.kind, value: c.value }; });
    send(JSON.stringify({ phase: "scan", values: VALUES, scanned_mb: report.scanned_mb, hits: report.hits.length }));
    // Watch: log the first change of every candidate.
    const state = candidates.map(function (c) {
        let initial = null;
        try {
            initial = c.kind.indexOf("f32") === 0
                ? readFloat(c.address, c.kind === "f32le")
                : readInt(c.address, c.kind);
        } catch (e) { initial = null; }
        return { c: c, initial: initial, reported: false };
    });
    const deadline = Date.now() + WATCH_S * 1000;
    const timer = setInterval(function () {
        for (const s of state) {
            if (s.reported) continue;
            let now = null;
            try {
                now = s.c.kind.indexOf("f32") === 0
                    ? readFloat(s.c.address, s.c.kind === "f32le")
                    : readInt(s.c.address, s.c.kind);
            } catch (e) { continue; }
            if (now !== s.initial) {
                s.reported = true;
                send(JSON.stringify({ phase: "change", address: s.c.address.toString(), kind: s.c.kind,
                                      from: s.initial, to: now, candidates_near: nearby(s.c.address) }));
            }
        }
        if (Date.now() > deadline) { clearInterval(timer); watchTimer = null; send(JSON.stringify({ phase: "done", watched: state.length })); }
    }, 700);
    watchTimer = timer;
}

function readInt(addr, little) {
    const buf = addr.readByteArray(4);
    const view = new DataView(buf);
    return view.getUint32(0, little);
}
function readFloat(addr, little) {
    const buf = addr.readByteArray(4);
    return new DataView(buf).getFloat32(0, little);
}
function nearby(addr) {
    const out = [];
    for (const c of candidates) {
        if (c.address.equals(addr)) continue;
        const d = c.address.sub(addr).toInt32();
        if (Math.abs(d) < 0x20000) out.push({ address: c.address.toString(), delta: d, kind: c.kind });
    }
    return out;
}

rpc.exports = {
    install: function () { installed = true; setTimeout(main, 500); return true; },
    stop: function () { if (watchTimer !== null) { clearInterval(watchTimer); watchTimer = null; } return "stopped installed=" + installed + " candidates=" + candidates.length; },
    total: function () { return candidates.length; },
};
