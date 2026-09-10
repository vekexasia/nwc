// Record-layer probe: log the readers that delimit records so the payload length of every
// record type can be derived. Read-only. Hooks the byte primitives and keeps only the call
// sites that belong to the record parser, logging the cursor windows before and after.
const mod = Process.findModuleByName("NewWorld.exe") ||
    Process.enumerateModules().find(m => m.name.toLowerCase().indexOf("newworld") >= 0);
if (mod === null) throw new Error("NewWorld.exe module not found");
const BASE = mod.base;
const WANT = [
    "0x6af2134",  // V1 varint
    "0x6af237f",  // V2 varint
    "0x61ad00f",  // type reference
    "0x2a4371a",  // flag byte copy, n = 1
    "0x6ae4541",  // frame marker / sequence
    "0x6a6ddda", "0x6a6de19", "0x6b079e2",  // length and constant bytes
];
const buf = [];
let armed = false, timer = null, total = 0, kept = 0;
function flush() { if (buf.length) send({ type: "record_samples", count: buf.length, items: buf.splice(0, buf.length) }); }
function windowAt(ctx) {
    try {
        const cursor = ctx.add(0x10).readPointer();
        return [cursor.toString(), Array.from(new Uint8Array(cursor.readByteArray(16)))
            .map(b => b.toString(16).padStart(2, "0")).join("")];
    } catch (e) { return ["", ""]; }
}
function hook(fn, tag) {
    Interceptor.attach(BASE.add(fn), {
        onEnter(args) { this.a = [args[0], args[1], args[2], args[3]]; this.n = args[2]; },
        onLeave() {
            total++;
            const caller = this.returnAddress.sub(BASE).toString();
            if (WANT.indexOf(caller) < 0) return;
            if (buf.length > 6000) return;
            let size = null;
            try { size = this.n.toInt32(); } catch (e) { size = null; }
            const w3 = windowAt(this.a[3]);
            const w0 = windowAt(this.a[0]);
            kept++;
            buf.push([Date.now(), tag, caller, size, w3[0], w3[1], w0[0], w0[1]]);
            if (buf.length >= 200) flush();
        }
    });
}
function arm() {
    if (armed) return "already-armed";
    armed = true;
    hook(0x87a190, "U8"); hook(0x87a1c0, "U16"); hook(0x87a220, "U32");
    hook(0x87b5c0, "V"); hook(0x87b770, "MASK"); hook(0x878610, "COPY");
    timer = setInterval(flush, 1000);
    return "armed";
}
rpc.exports = {
    install: function () { return arm(); },
    stop: function () { if (timer) clearInterval(timer); flush(); return "stopped total=" + total + " kept=" + kept; },
    total: function () { return total; },
};
