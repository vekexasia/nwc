// Probe: log every raw serialization write in order, with sink, caller and timestamp.
// Runs alongside the auto-prepended DTLS ledger hooks (same Frida attach).
const mod = Process.findModuleByName("NewWorld.exe") || Process.enumerateModules().find(m => m.name.toLowerCase().indexOf("newworld") >= 0);
if (mod === null) throw new Error("NewWorld.exe module not found");
const BASE = mod.base;
const WRITE_FN = BASE.add(0x87bcc0);

const buf = [];
let total = 0;
let armed = false;
let timer = null;

function flush() {
    if (buf.length === 0) return;
    send({ type: "trace_writes", count: buf.length, writes: buf.splice(0, buf.length) });
}

function arm() {
    if (armed) return "already-armed";
    armed = true;
    Interceptor.attach(WRITE_FN, {
        onEnter(args) {
            total++;
            try {
                const sink = args[0];
                const src = args[1];
                const n = args[2].toInt32();
                const take = n > 0 ? Math.min(n, 64) : 0;
                const hex = take > 0 ? Array.from(new Uint8Array(src.readByteArray(take)))
                    .map(b => b.toString(16).padStart(2, "0")).join("") : "";
                buf.push([Date.now(), sink.toString(), this.returnAddress.sub(BASE).toString(), n, hex]);
                if (buf.length >= 500) flush();
            } catch (e) { /* unreadable pointer: skip this write */ }
        }
    });
    timer = setInterval(flush, 1000);
    return "armed";
}

rpc.exports = {
    install: function () { return arm(); },
    stop: function () { if (timer) clearInterval(timer); flush(); return "stopped total=" + total; },
    total: function () { return total; },
};
