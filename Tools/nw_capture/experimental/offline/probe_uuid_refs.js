// Capture what the 16-byte reference reader (FUN_1461acfe0) yields: for calls from 0x61ad00f
// log the index varint and, when a raw 16-byte read follows, the bytes that land in the
// destination buffer. Those 16 bytes are checked offline against the live registry's uuids.
const mod = Process.findModuleByName("NewWorld.exe") || Process.enumerateModules().find(m => m.name.toLowerCase().indexOf("newworld") >= 0);
if (mod === null) throw new Error("NewWorld.exe module not found");
const BASE = mod.base;
const REF_CALLER = BASE.add(0x61ad00f).toString();
const buf = [];
let armed = false, timer = null;
function flush() { if (buf.length) send({ type: "uuid_refs", count: buf.length, items: buf.splice(0, buf.length) }); }
function hexOf(ptr, n) {
    try { return Array.from(new Uint8Array(ptr.readByteArray(n))).map(b => b.toString(16).padStart(2, "0")).join(""); }
    catch (e) { return ""; }
}
function arm() {
    if (armed) return "already-armed";
    armed = true;
    Interceptor.attach(BASE.add(0x87b5c0), {
        onEnter(args) { this.caller = this.returnAddress.toString(); this.out = args[2]; },
        onLeave() {
            if (this.caller !== REF_CALLER) return;
            if (buf.length > 6000) return;
            try { buf.push([Date.now(), "idx", this.out.readU32(), "", ""]); } catch (e) { }
        }
    });
    Interceptor.attach(BASE.add(0x878610), {
        onEnter(args) { this.caller = this.returnAddress.toString(); this.dst = args[1]; this.n = args[2].toInt32(); },
        onLeave() {
            if (this.caller !== REF_CALLER || this.n !== 16) return;
            if (buf.length > 6000) return;
            buf.push([Date.now(), "raw16", 0, this.dst.toString(), hexOf(this.dst, 16)]);
        }
    });
    timer = setInterval(flush, 1000);
    return "armed";
}
rpc.exports = {
    install: function () { return arm(); },
    stop: function () { if (timer) clearInterval(timer); flush(); return "stopped"; },
    total: function () { return buf.length; },
};
