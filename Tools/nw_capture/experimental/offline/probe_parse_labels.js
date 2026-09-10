// Probe: label inbound parses. Hooks the read driver 0x146160ae0, whose first argument is the
// value object; its first qword is the vtable, and in this build each vtable is followed in
// .rdata by the inline type name. Also records the caller (the registry handler) and, when
// readable, the reader context cursor/end.
const mod = Process.findModuleByName("NewWorld.exe") || Process.enumerateModules().find(m => m.name.toLowerCase().indexOf("newworld") >= 0);
if (mod === null) throw new Error("NewWorld.exe module not found");
const BASE = mod.base;

const buf = [];
let total = 0, armed = false, timer = null;
function flush() { if (buf.length) send({ type: "parse_labels", count: buf.length, events: buf.splice(0, buf.length) }); }

function arm() {
    if (armed) return "already-armed";
    armed = true;
    Interceptor.attach(BASE.add(0x6160ae0), {
        onEnter(args) {
            total++;
            try {
                const value = args[0];
                const vt = value.readPointer();
                const decoder = args[2];
                let cursor = -1, end = -1;
                try {
                    cursor = decoder.add(0x10).readPointer().toInt32();
                    end = decoder.add(0x08).readPointer().toInt32();
                } catch (e) { /* decoder layout may differ */ }
                buf.push([Date.now(), vt.sub(BASE).toString(), this.returnAddress.sub(BASE).toString(),
                          cursor, end]);
                if (buf.length >= 400) flush();
            } catch (e) { /* skip */ }
        }
    });
    timer = setInterval(flush, 1000);
    return "armed";
}
rpc.exports = {
    install: function () { return arm(); },
    stop: function () { if (timer) clearInterval(timer); flush(); return "stopped events=" + total; },
    total: function () { return total; },
};
