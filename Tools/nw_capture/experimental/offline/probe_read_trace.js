// Probe: log every bounded byte read and every prefix-coded varint decode on the inbound path.
// 0x140878610(reader, dst, n, ok) with reader+0x08 = end, reader+0x10 = cursor.
// 0x14087b5c0(?, status, out_uint, reader) decodes the prefix-coded varint.
const mod = Process.findModuleByName("NewWorld.exe") || Process.enumerateModules().find(m => m.name.toLowerCase().indexOf("newworld") >= 0);
if (mod === null) throw new Error("NewWorld.exe module not found");
const BASE = mod.base;

const buf = [];
let totalReads = 0, totalVarints = 0;
let armed = false, timer = null;

function flush() {
    if (buf.length === 0) return;
    send({ type: "trace_reads", count: buf.length, reads: buf.splice(0, buf.length) });
}

function arm() {
    if (armed) return "already-armed";
    armed = true;
    Interceptor.attach(BASE.add(0x878610), {
        onEnter(args) {
            totalReads++;
            try {
                const ctx = args[0];
                const n = args[2].toInt32();
                const cursor = ctx.add(0x10).readPointer();
                const end = ctx.add(0x08).readPointer();
                let hex = "";
                if (n > 0 && n <= 64) {
                    hex = Array.from(new Uint8Array(cursor.readByteArray(n)))
                        .map(b => b.toString(16).padStart(2, "0")).join("");
                }
                buf.push([Date.now(), "R", ctx.toString(), cursor.toString(), end.sub(cursor).toInt32(),
                          n, this.returnAddress.sub(BASE).toString(), hex]);
                if (buf.length >= 400) flush();
            } catch (e) { /* skip */ }
        }
    });
    Interceptor.attach(BASE.add(0x87b5c0), {
        onEnter(args) { this.outPtr = args[2]; },
        onLeave(retval) {
            totalVarints++;
            try {
                if (buf.length > 4000) return;
                buf.push([Date.now(), "V", this.outPtr.toString(), "", 0, 0,
                          this.returnAddress.sub(BASE).toString(), this.outPtr.readU32().toString()]);
            } catch (e) { /* skip */ }
        }
    });
    timer = setInterval(flush, 1000);
    return "armed";
}

rpc.exports = {
    install: function () { return arm(); },
    stop: function () { if (timer) clearInterval(timer); flush(); return "stopped reads=" + totalReads + " varints=" + totalVarints; },
    total: function () { return totalReads; },
};
