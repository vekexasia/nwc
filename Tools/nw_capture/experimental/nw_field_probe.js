// Probe for the walk test: log the values of the candidate coordinate field reader while the
// game runs. It hooks the u16 reader and keeps only the call sites we care about, plus the
// neighbours that read adjacent fields, so their co-movement can be checked. Read-only.
const mod = Process.findModuleByName("NewWorld.exe") || Process.enumerateModules().find(m => m.name.toLowerCase().indexOf("newworld") >= 0);
if (mod === null) throw new Error("NewWorld.exe module not found");
const BASE = mod.base;
// candidate coordinate readers: u16 family plus the u32/u8 neighbours seen in ALC payloads
const WANT = ["0x2a42e2e", "0x4042e05", "0x4042b18", "0x2a42e7e", "0x2a42d65", "0x2a42ed5",
              "0x2a42dc5", "0x2a432ea", "0x279e22e", "0x6a6deca"];
const buf = [];
let armed = false, timer = null, total = 0, kept = 0;
function flush() { if (buf.length) send({ type: "field_samples", count: buf.length, items: buf.splice(0, buf.length) }); }
function windowAt(ctx) {
    try {
        const cursor = ctx.add(0x10).readPointer();
        return [cursor.toString(), Array.from(new Uint8Array(cursor.sub(8).readByteArray(24))).map(b => b.toString(16).padStart(2, "0")).join("")];
    } catch (e) { return ["", ""]; }
}
function hook(fn, tag) {
    Interceptor.attach(BASE.add(fn), {
        onEnter(args) { this.ctx = args[3]; },
        onLeave() {
            total++;
            const caller = this.returnAddress.sub(BASE).toString();
            if (WANT.indexOf(caller) < 0) return;
            if (buf.length > 4000) return;
            const [cur, win] = windowAt(this.ctx);
            kept++;
            buf.push([Date.now(), tag, caller, cur, win]);
            if (buf.length >= 200) flush();
        }
    });
}
function arm() {
    if (armed) return "already-armed";
    armed = true;
    hook(0x87a190, "U8"); hook(0x87a1c0, "U16"); hook(0x87a220, "U32"); hook(0x87b5c0, "V");
    timer = setInterval(flush, 1000);
    return "armed";
}
rpc.exports = {
    install: function () { return arm(); },
    stop: function () { if (timer) clearInterval(timer); flush(); return "stopped total=" + total + " kept=" + kept; },
    total: function () { return total; },
};
