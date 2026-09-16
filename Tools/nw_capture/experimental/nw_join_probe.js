// Join probe: one line per replicated-state chunk, with the record header that groups the chunks
// of one entity. Read-only.
//
// Record layer (FUN_146af20d0, RVA 0x6af20d0): reads V1 (prefix varint -> u16 out at args[1]),
// a u8 chunk count, then per chunk FUN_146af2340 (RVA 0x6af2340): V2 varint, type reference,
// object factory, then object->vtable[0x90](object, ctx) consumes exactly that state's payload and
// {V2, object} is pushed onto the vector at args[1] (24-byte entries: u32 V2, +8 object).
// The reader ctx is *args[0]; its cursor is ctx+0x10. So one hook pair gives, per chunk: V1, V2,
// typeIndex (parsed from the bytes), the object address and the exact payload bytes.
const mod = Process.findModuleByName("NewWorld.exe") ||
    Process.enumerateModules().find(m => m.name.toLowerCase().indexOf("newworld") >= 0);
if (mod === null) throw new Error("NewWorld.exe module not found");
const BASE = mod.base;
const installCapture = rpc.exports.install;
const stopCapture = rpc.exports.stop;
const RECORD_FN = 0x6af20d0, CHUNK_FN = 0x6af2340;
const PLAYER_TYPE = 3935, VITALS_TYPE = 15, PLAYER_NAME_FIELD = 0x870 + 0x10;   // docs/Network/player-component.md
const TYPE_REF = 0x61acfe0, VARINT = 0x87b5c0, TYPE_REF_VARINT_SITE = 0x61ad00f;
const lastType = {};
// replicated states seen so far: their chunks already go out as join_samples
const STATE_TYPES = new Set([10, 12, 13, 15, 16, 81, 100, 129, 185, 205, 497, 603, 670, 899, 911, 982, 1195, 1525, 1528, 1566,
    1594, 1652, 1739, 1755, 1927, 1994, 2187, 2267, 2406, 2768, 2850, 2895, 2912, 2913, 2930, 2932, 2938, 3086, 3133, 3139,
    3147, 3152, 3183, 3210, 3290, 3312, 3362, 3408, 3563, 3652, 3663, 3681, 3752, 3765, 3780, 3786, 3791, 3829, 3935,
    4176, 4236, 4297, 4321, 4878, 4896, 4913, 5027, 5257, 5437, 5485, 5606, 5620, 5691, 6234, 6951]);
const POS_ABS_READER = 0x2a433d0;    // worldPosAbs field reader: 10 wire bytes at ctx+0x10 (nw_pos_probe.js)
const PLAYER_ID_FIELD = 0x7c0;
const MAX_HEX = 200;
const MAX_FRAGMENT_BODY = 8192, FRAGMENT_BATCH_BYTES_MAX = 256 * 1024;
const FRAGMENT_ITEM_OVERHEAD_MAX = 192;
const perThread = {};
// join_samples is the raw evidence; the other three are the shapes nw_live.py already reads,
// keyed by entity ("e<V1>") instead of by a transient object address.
const buffers = { join_samples: [], pos_samples: [], vitals_samples: [], player_samples: [], rmi_samples: [] };
const fragmentBuffer = [];
const fragmentStats = { captured: 0, sent: 0, batches: 0, dropped: 0, oversized: 0, refused: 0 };
let fragmentBufferBytes = 0;
let armed = false, timer = null, chunks = 0, records = 0;

function emit(kind, item) {
    const buf = buffers[kind];
    if (buf.length > 6000) return;
    buf.push(item);
    if (buf.length >= 200) flush();
}
function flushFragments() {
    if (!fragmentBuffer.length) return;
    const items = fragmentBuffer.splice(0, fragmentBuffer.length);
    const encodedBytes = fragmentBufferBytes;
    fragmentBufferBytes = 0;
    try {
        send({ type: "fragment_samples", count: items.length, encoded_bytes: encodedBytes, items });
        fragmentStats.sent += items.length;
        fragmentStats.batches++;
    } catch (e) {
        fragmentStats.dropped += items.length;
    }
}
function emitFragment(item, encodedBytes) {
    if (encodedBytes > FRAGMENT_BATCH_BYTES_MAX) {
        fragmentStats.dropped++;
        return;
    }
    if (fragmentBufferBytes + encodedBytes > FRAGMENT_BATCH_BYTES_MAX) flushFragments();
    fragmentBuffer.push(item);
    fragmentBufferBytes += encodedBytes;
    fragmentStats.captured++;
}
function captureFragment(v1, v2, typeIndex, object, bodyAt, bodyLength) {
    if (bodyLength <= 0) return;
    if (v1 < 0) {
        fragmentStats.dropped++;
        return;
    }
    if (bodyLength > MAX_FRAGMENT_BODY) {
        fragmentStats.oversized++;
        return;
    }
    try {
        const classAddress = object.readPointer();
        const decoderAddress = classAddress.add(0x90).readPointer();
        const moduleEnd = BASE.add(mod.size);
        if (classAddress.compare(BASE) < 0 || classAddress.compare(moduleEnd) >= 0
                || decoderAddress.compare(BASE) < 0 || decoderAddress.compare(moduleEnd) >= 0) {
            fragmentStats.dropped++;
            return;
        }
        const body = hex(new Uint8Array(bodyAt.readByteArray(bodyLength)));
        emitFragment({
            key: v2,
            v1,
            v2,
            type: typeIndex,
            class: classAddress.sub(BASE).toUInt32(),
            decoder: decoderAddress.sub(BASE).toUInt32(),
            accepted: true,
            body,
        }, 2 * bodyLength + FRAGMENT_ITEM_OVERHEAD_MAX);
    } catch (e) {
        fragmentStats.dropped++;
    }
}
function flush() {
    for (const kind in buffers) {
        const buf = buffers[kind];
        if (buf.length) send({ type: kind, count: buf.length, items: buf.splice(0, buf.length) });
    }
    flushFragments();
}
function currentV1(threadId) { const p = perThread[threadId]; return p ? p.readU16() : -1; }
function hexAt(address, size) { return hex(new Uint8Array(address.readByteArray(size))); }
function prefixVarint(bytes, o) {     // FUN_14087b5c0, same branches as decode_alc_state.read_prefix_varint
    const b = bytes[o];
    if (b < 0x80) return [b, 1];
    if (b < 0xc0) return [(bytes[o + 1] << 6) | (b & 0x3f), 2];
    if (b < 0xe0) return [(((bytes[o + 1] << 8) | bytes[o + 2]) << 5) | (b & 0x1f), 3];
    if (b < 0xf0) return [(((bytes[o + 1] << 16) | (bytes[o + 2] << 8) | bytes[o + 3]) << 4) | (b & 0x0f), 4];
    return [(((bytes[o + 1] << 24) | (bytes[o + 2] << 16) | (bytes[o + 3] << 8) | bytes[o + 4]) << 3) | (b & 0x07), 5];
}
function hex(u8) { return Array.from(u8).map(b => b.toString(16).padStart(2, "0")).join(""); }
function readName(object) {
    try {
        const raw = new Uint8Array(object.add(PLAYER_NAME_FIELD).readByteArray(48));
        let text = "";
        for (const byte of raw) { if (byte === 0 || byte < 0x20 || byte > 0x7e) break; text += String.fromCharCode(byte); }
        return text;
    } catch (e) { return ""; }
}
function arm() {
    if (armed) return "already-armed";
    armed = true;
    Interceptor.attach(BASE.add(RECORD_FN), {
        onEnter(args) { records++; perThread[this.threadId] = args[1]; },
        onLeave() { delete perThread[this.threadId]; }
    });
    Interceptor.attach(BASE.add(CHUNK_FN), {
        onEnter(args) {
            try {
                this.vec = args[1];
                this.ctx = args[0].readPointer();
                this.before = this.ctx.add(0x10).readPointer();
            } catch (e) { this.before = null; }
        },
        onLeave(retval) {
            chunks++;
            if (this.before === null) return;
            if ((retval.toInt32() & 0xff) === 0) {
                fragmentStats.refused++;
                return;
            }
            try {
                const after = this.ctx.add(0x10).readPointer();
                const total = after.sub(this.before).toInt32();
                if (total <= 0 || total > 0x40000) return;
                const head = new Uint8Array(this.before.readByteArray(Math.min(total, 12)));
                const [v2, n2] = prefixVarint(head, 0);
                const [typeIndex, nt] = prefixVarint(head, n2);
                const payloadAt = n2 + nt;
                const payloadLen = total - payloadAt;
                const shown = Math.min(payloadLen, MAX_HEX);
                const payload = shown > 0 ? hex(new Uint8Array(this.before.add(payloadAt).readByteArray(shown))) : "";
                const end = this.vec.add(8).readPointer();
                const entry = end.sub(0x18);
                const object = entry.add(8).readPointer();
                const v1 = currentV1(this.threadId), key = "e" + v1, now = Date.now();
                const item = [now, v1, v2, typeIndex, object.toString(), payloadLen, payload];
                if (typeIndex === PLAYER_TYPE) {
                    const name = readName(object);
                    item.push(name);
                    // a delta chunk carries no name; only the full state (entity enters scope) does
                    if (name) emit("player_samples", [now, key, name, hexAt(object.add(PLAYER_ID_FIELD), 16)]);
                } else if (typeIndex === VITALS_TYPE) {
                    emit("vitals_samples", [now, key, payload]);
                }
                emit("join_samples", item);
                const fragmentPayloadAt = payloadAt + (typeIndex === 0 ? 16 : 0);
                captureFragment(v1, v2, typeIndex, object,
                    this.before.add(fragmentPayloadAt), total - fragmentPayloadAt);
            } catch (e) { }
        }
    });
    // typed messages that are not replicated-state chunks (client-facet RMIs, Ping, TimeSynch): the type
    // reference reader FUN_1461acfe0 sees every type on the wire; keep the ones the chunk hook does not,
    // with the bytes that follow the reference (the message body). nw_rmi_probe.js is the standalone form.
    Interceptor.attach(BASE.add(VARINT), {
        onEnter(args) { this.out = args[2]; },
        onLeave() {
            if (this.returnAddress.sub(BASE).toInt32() !== TYPE_REF_VARINT_SITE) return;
            try { lastType[this.threadId] = this.out.readU32(); } catch (e) { }
        }
    });
    Interceptor.attach(BASE.add(TYPE_REF), {
        onEnter(args) { this.ctx = args[2]; },
        onLeave() {
            const typeIndex = lastType[this.threadId];
            if (typeIndex === undefined || STATE_TYPES.has(typeIndex) || typeIndex === 8 || typeIndex === 11) return;
            try {
                const cursor = this.ctx.add(0x10).readPointer(), end = this.ctx.add(0x08).readPointer();
                const n = Math.min(512, end.sub(cursor).toInt32());   // 160 cut the warboard and inventory records
                emit("rmi_samples", [Date.now(), typeIndex, n > 0 ? hexAt(cursor, n) : ""]);
            } catch (e) { }
        }
    });
    Interceptor.attach(BASE.add(POS_ABS_READER), {
        onEnter(args) {
            try {
                const cursor = args[1].add(0x10).readPointer();
                emit("pos_samples", [Date.now(), "ABS", "e" + currentV1(this.threadId), hexAt(cursor, 10)]);
            } catch (e) { }
        }
    });
    timer = setInterval(flush, 500);
    return "armed";
}
rpc.exports.install = function () {
    if (typeof installCapture === "function") installCapture();
    return arm();
};
rpc.exports.stop = function () {
    if (timer) clearInterval(timer);
    flush();
    send({ type: "fragment_stats", ...fragmentStats });
    if (typeof stopCapture === "function") stopCapture();
    return "stopped records=" + records + " chunks=" + chunks;
};
rpc.exports.total = function () { return chunks; };
