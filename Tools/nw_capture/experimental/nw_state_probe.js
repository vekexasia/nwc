// Which replicated states does the parser actually decode for this player?
// Hooks each state's unmarshal (addresses from the census: list_replicated_states.py) and logs
// how many bytes it consumed. Every entry is logged even when no cursor can be found, so a
// "the function never fires" conclusion is distinguishable from "the hook is wrong".
// Read-only: only the reader cursor is read, before and after the call.
const mod = Process.findModuleByName("NewWorld.exe") ||
    Process.enumerateModules().find(m => m.name.toLowerCase().indexOf("newworld") >= 0);
if (mod === null) throw new Error("NewWorld.exe module not found");
const BASE = mod.base;
const STATES = {
    "0x2a327f0": "ALCReplicatedState",
    "0x65b0dd0": "VitalsComponentReplicatedState",
    "0x659bbf0": "DamageReceiverComponentReplicatedState",
    "0x65b5ea0": "GritReplicatedState",
    "0x5ce5f90": "PositionInTheWorldReplicatedState",
    "0x5ce5f30": "GatherableControllerReplicatedState",
    "0x65a60b0": "ProjectileReplicatedState",
};
const buf = [];
const calls = {};
let timer = null, armed = false, entries = 0, withCursor = 0;

function flush() { if (buf.length) send({ type: "state_calls", count: buf.length, totals: calls, items: buf.splice(0, buf.length) }); }
function cursorOf(arg) {
    try {
        const cursor = arg.add(0x10).readPointer();
        // a plausible cursor lives in a mapped range and is not zero
        if (cursor.isNull() || cursor.compare(ptr(0x1000)) < 0) return null;
        return cursor;
    } catch (e) { return null; }
}
function hook(rva, name) {
    Interceptor.attach(BASE.add(parseInt(rva, 16)), {
        onEnter(args) {
            entries++;
            calls[name] = (calls[name] || 0) + 1;
            this.ctx = null; this.before = null; this.rawArgs = [];
            for (let i = 0; i < 4; i++) {
                const a = args[i];
                this.rawArgs.push(a ? a.toString() : "0");
                if (this.ctx === null && a) {
                    const c = cursorOf(a);
                    if (c) { this.ctx = a; this.before = c; }
                }
            }
            if (this.before === null) {
                buf.push([Date.now(), name, -1, "", this.rawArgs.join(",")]);
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
            buf.push([Date.now(), name, consumed, raw, this.rawArgs.join(",")]);
            if (buf.length >= 100) flush();
        }
    });
}
rpc.exports = {
    install: function () {
        if (armed) return "already-armed";
        armed = true;
        for (const rva in STATES) hook(rva, STATES[rva]);
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
