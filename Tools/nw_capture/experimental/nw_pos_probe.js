// Probe the two world-position field readers of ALCReplicatedState, identified statically:
//   0x142a433d0 = worldPosAbs : 10 wire bytes (two byte-swapped float32 + one quantised u16)
//   0x142a43330 = worldPosRel : 3 wire bytes (three quantised deltas, 0xff = no update)
// The field readers are called as reader(descriptor, reader_ctx); the bytes they consume start at
// reader_ctx+0x10. Read-only.
const mod = Process.findModuleByName("NewWorld.exe") || Process.enumerateModules().find(m => m.name.toLowerCase().indexOf("newworld") >= 0);
if (mod === null) throw new Error("module not found");
const BASE = mod.base;
const buf = [];
let armed = false, timer = null, nAbs = 0, nRel = 0;
function flush() { if (buf.length) send({ type: "pos_samples", count: buf.length, items: buf.splice(0, buf.length) }); }
function hook(addr, tag, size, counter) {
    Interceptor.attach(BASE.add(addr), {
        onEnter(args) {
            if (buf.length > 4000) return;
            try {
                const ctx = args[1];
                const cursor = ctx.add(0x10).readPointer();
                const bytes = Array.from(new Uint8Array(cursor.readByteArray(size)))
                    .map(b => b.toString(16).padStart(2, "0")).join("");
                counter.n++;
                buf.push([Date.now(), tag, bytes, cursor.toString()]);
            } catch (e) { }
        }
    });
}
function arm() {
    if (armed) return "already-armed";
    armed = true;
    hook(0x2a433d0, "ABS", 10, { get n() { return nAbs; }, set n(v) { nAbs = v; } });
    hook(0x2a43330, "REL", 3, { get n() { return nRel; }, set n(v) { nRel = v; } });
    timer = setInterval(flush, 1000);
    return "armed";
}
rpc.exports = {
    install: function () { return arm(); },
    stop: function () { if (timer) clearInterval(timer); flush(); return "stopped abs=" + nAbs + " rel=" + nRel; },
    total: function () { return nAbs + nRel; },
};
