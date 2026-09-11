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
const RECORD_FN = 0x6af20d0, CHUNK_FN = 0x6af2340;
const PLAYER_TYPE = 3935, VITALS_TYPE = 15, PLAYER_NAME_FIELD = 0x870 + 0x10;   // docs/Network/player-component.md
const POS_ABS_READER = 0x2a433d0;    // worldPosAbs field reader: 10 wire bytes at ctx+0x10 (nw_pos_probe.js)
const PLAYER_ID_FIELD = 0x7c0;
const MAX_HEX = 200;
const perThread = {};
// join_samples is the raw evidence; the other three are the shapes nw_live.py already reads,
// keyed by entity ("e<V1>") instead of by a transient object address.
const buffers = { join_samples: [], pos_samples: [], vitals_samples: [], player_samples: [] };
let armed = false, timer = null, chunks = 0, records = 0;

function emit(kind, item) {
    const buf = buffers[kind];
    if (buf.length > 6000) return;
    buf.push(item);
    if (buf.length >= 200) flush();
}
function flush() {
    for (const kind in buffers) {
        const buf = buffers[kind];
        if (buf.length) send({ type: kind, count: buf.length, items: buf.splice(0, buf.length) });
    }
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
            if (this.before === null || (retval.toInt32() & 0xff) === 0) return;
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
rpc.exports = {
    install: function () { return arm(); },
    stop: function () { if (timer) clearInterval(timer); flush(); return "stopped records=" + records + " chunks=" + chunks; },
    total: function () { return chunks; },
};
