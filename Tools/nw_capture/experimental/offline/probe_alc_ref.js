// Decisive check: hook FUN_1461acfe0 (the 16-byte reference reader) and record, for every call,
// (a) the varint bytes at the reader cursor BEFORE the call consumes them, and (b) the 16 bytes
// the function writes to its destination. If, for index i, the destination equals the live
// registry's uuid for typeIndex i, then the wire value is literally a registry typeIndex.
const mod = Process.findModuleByName("NewWorld.exe") || Process.enumerateModules().find(m => m.name.toLowerCase().indexOf("newworld") >= 0);
if (mod === null) throw new Error("NewWorld.exe module not found");
const BASE = mod.base;
const buf = [];
let armed = false, timer = null;
function flush() { if (buf.length) send({ type: "alc_ref", count: buf.length, items: buf.splice(0, buf.length) }); }
function hex(ptr, n) { try { return Array.from(new Uint8Array(ptr.readByteArray(n))).map(b => b.toString(16).padStart(2, "0")).join(""); } catch (e) { return ""; } }
function arm() {
    if (armed) return "already-armed";
    armed = true;
    Interceptor.attach(BASE.add(0x61acfe0), {
        onEnter(args) {
            this.dst = args[1];
            try {
                const ctx = args[2];
                const cursor = ctx.add(0x10).readPointer();
                this.varintHex = hex(cursor, 5);
            } catch (e) { this.varintHex = ""; }
        },
        onLeave() {
            if (buf.length > 6000) return;
            buf.push([Date.now(), this.varintHex, hex(this.dst, 16)]);
        }
    });
    timer = setInterval(flush, 1000);
    return "armed";
}
rpc.exports = { install: function () { return arm(); },
                stop: function () { if (timer) clearInterval(timer); flush(); return "stopped"; },
                total: function () { return buf.length; } };
