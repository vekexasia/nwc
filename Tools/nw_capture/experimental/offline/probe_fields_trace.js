// Field-level inbound trace v2: every varint decode and every bounded read, with the reader
// cursor and a 48-byte window (16 before the cursor, 32 after) so each event can be located
// unambiguously inside a captured ledger stream offline.
const mod = Process.findModuleByName("NewWorld.exe") || Process.enumerateModules().find(m => m.name.toLowerCase().indexOf("newworld") >= 0);
if (mod === null) throw new Error("NewWorld.exe module not found");
const BASE = mod.base;
const buf = [];
let nv = 0, nf = 0, armed = false, timer = null;
function flush() { if (buf.length) send({ type: "fields2", count: buf.length, items: buf.splice(0, buf.length) }); }
function windowAt(ptr) {
    try {
        return Array.from(new Uint8Array(ptr.sub(16).readByteArray(48)))
            .map(b => b.toString(16).padStart(2, "0")).join("");
    } catch (e) { return ""; }
}
function arm() {
    if (armed) return "already-armed";
    armed = true;
    Interceptor.attach(BASE.add(0x87b5c0), {
        onEnter(args) { this.ctx = args[3]; this.out = args[2]; },
        onLeave() {
            nv++;
            if (buf.length > 12000) return;
            try {
                const cursor = this.ctx.add(0x10).readPointer();
                buf.push([Date.now(), "V", this.returnAddress.sub(BASE).toString(),
                          this.out.readU32(), cursor.toString(), windowAt(cursor)]);
            } catch (e) { }
        }
    });
    Interceptor.attach(BASE.add(0x878610), {
        onEnter(args) {
            nf++;
            if (buf.length > 12000) return;
            try {
                const ctx = args[0], n = args[2].toInt32();
                const cursor = ctx.add(0x10).readPointer();
                buf.push([Date.now(), "F" + n, this.returnAddress.sub(BASE).toString(),
                          0, cursor.toString(), windowAt(cursor)]);
                if (buf.length >= 400) flush();
            } catch (e) { }
        }
    });
    timer = setInterval(flush, 1000);
    return "armed";
}
rpc.exports = {
    install: function () { return arm(); },
    stop: function () { if (timer) clearInterval(timer); flush(); return "stopped v=" + nv + " f=" + nf; },
    total: function () { return nv + nf; },
};
