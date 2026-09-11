// Which replicated states does the parser actually decode for this player?
// Hooks each state's unmarshal (addresses from the census: list_replicated_states.py) and logs
// how many bytes it consumed. Every entry is logged even when no cursor can be found, so a
// "the function never fires" conclusion is distinguishable from "the hook is wrong".
// Read-only: only the reader cursor is read, before and after the call.
const mod = Process.findModuleByName("NewWorld.exe") ||
    Process.enumerateModules().find(m => m.name.toLowerCase().indexOf("newworld") >= 0);
if (mod === null) throw new Error("NewWorld.exe module not found");
const BASE = mod.base;
const STATES = {   // RVAs, i.e. absolute address minus the image base 0x140000000
    "0x2a433d0": "CONTROL-worldPosAbs-reader",
    "0x6160ae0": "Vitals-deserialiser-3stage",
    "0x17b4110": "Vitals-stage-90-mask",
    "0x17b3e90": "Vitals-stage-a0-member",
    "0x17b4320": "Vitals-stage-b0-delta",
    "0x671e040": "Vitals-object-builder",
    "0x65b0dd0": "Vitals-registry-unmarshal",
};
const buf = [];
const calls = {};
let timer = null, armed = false, entries = 0, withCursor = 0;

function flush() { if (buf.length) send({ type: "state_calls", count: buf.length, totals: calls, items: buf.splice(0, buf.length) }); }
function cursorOf(arg) {
    try {
        const cursor = arg.add(0x10).readPointer();
        if (cursor.isNull() || cursor.compare(ptr(0x1000)) < 0) return null;
        return cursor;
    } catch (e) { return null; }
}
function ctxOf(args) {            // the reader context of these state readers is arg 1 or 2
    for (const i of [1, 2, 0, 3]) {
        const c = cursorOf(args[i]);
        if (c !== null) return [args[i], c];
    }
    return [null, null];
}
function hook(rva, name) {
    Interceptor.attach(BASE.add(parseInt(rva, 16)), {
        onEnter(args) {
            entries++;
            calls[name] = (calls[name] || 0) + 1;
            this.obj = args[0] ? args[0].toString() : "";
            const found = ctxOf(args);
            this.ctx = found[0]; this.before = found[1];
            this.rawArgs = [this.obj];
            if (this.before === null) {
                buf.push([Date.now(), name, -1, this.obj, ""]);
                if (buf.length >= 100) flush();
            }
        },
        onLeave() {
            if (this.before === null) return;
            const after = cursorOf(this.ctx);
            if (after === null) return;
            const consumed = after.sub(this.before).toInt32();
            if (consumed < 0 || consumed > 8192) return;
            let raw = "";
            try {
                raw = Array.from(new Uint8Array(this.before.readByteArray(Math.min(consumed, 48))))
                    .map(b => b.toString(16).padStart(2, "0")).join("");
            } catch (e) { raw = ""; }
            withCursor++;
            buf.push([Date.now(), name, consumed, this.obj, raw]);
            if (buf.length >= 100) flush();
        }
    });
}
rpc.exports = {
    install: function () {
        if (armed) return "already-armed";
        armed = true;
        const failed = [];
        for (const rva in STATES) {
            try { hook(rva, STATES[rva]); }
            catch (e) { failed.push(rva + ":" + e); }
        }
        if (failed.length) send({ type: "hook_failures", items: failed });
        timer = setInterval(flush, 1000);
        return "armed " + Object.keys(STATES).length + " states";
    },
    stop: function () {
        if (timer) clearInterval(timer);
        flush();
        return "stopped entries=" + entries + " with_cursor=" + withCursor + " totals=" + JSON.stringify(calls);
    },
    total: function () { return entries; },
};
