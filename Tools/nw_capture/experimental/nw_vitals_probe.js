// Read the Vitals fields the way ALC was mapped: hook the byte primitives and keep the calls
// whose return address is inside the Vitals reader, so each field read shows its bytes.
// Read-only. No input, no focus needed.
const mod = Process.findModuleByName("NewWorld.exe") ||
    Process.enumerateModules().find(m => m.name.toLowerCase().indexOf("newworld") >= 0);
if (mod === null) throw new Error("NewWorld.exe module found");
const BASE = mod.base;
// Vitals reader functions (absolute addresses from the static analysis, minus the image base)
const VITALS = [[0x17b4110, "stage90"], [0x17b43c0, "masked-member"], [0x17b3e90, "stageA0"],
                [0x17b4320, "stageB0"], [0x17b3f00, "helper"]];
const buf = [];
const counts = {};
let timer = null, armed = false, seen = 0;
function flush() { if (buf.length) send({ type: "vitals_fields", count: buf.length, totals: counts, items: buf.splice(0, buf.length) }); }
function inVitals(rva) { return VITALS.some(v => rva >= v[0] && rva < v[0] + 0x400); }
function hook(fn, tag) {
    Interceptor.attach(BASE.add(fn), {
        onEnter(args) { this.ctx = args[3]; },
        onLeave() {
            const caller = this.returnAddress.sub(BASE).toInt32();
            if (!inVitals(caller)) return;
            let cur = null;
            try { cur = this.ctx.add(0x10).readPointer(); } catch (e) { return; }
            let raw = "";
            try {
                const back = cur.sub(8);
                raw = Array.from(new Uint8Array(back.readByteArray(16)))
                    .map(b => b.toString(16).padStart(2, "0")).join("");
            } catch (e) { raw = ""; }
            counts[tag] = (counts[tag] || 0) + 1;
            seen++;
            buf.push([Date.now(), tag, "0x" + caller.toString(16), cur.toString(), raw]);
            if (buf.length >= 100) flush();
        }
    });
}
rpc.exports = {
    install: function () {
        if (armed) return "already-armed";
        armed = true;
        const failed = [];
        for (const [addr, tag] of [[0x87a190, "U8"], [0x87a1c0, "U16"], [0x87a220, "U32"],
                                   [0x87b5c0, "V"], [0x87b770, "MASK"], [0x878610, "COPY"]]) {
            try { hook(addr, tag); } catch (e) { failed.push(tag + ":" + e); }
        }
        if (failed.length) send({ type: "hook_failures", items: failed });
        timer = setInterval(flush, 500);
        return "armed";
    },
    stop: function () { if (timer) clearInterval(timer); flush(); return "stopped seen=" + seen; },
    total: function () { return seen; },
};
