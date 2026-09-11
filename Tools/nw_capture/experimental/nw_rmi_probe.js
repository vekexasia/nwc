// RMI probe: which typed messages (client-facet RMIs, channel-0 messages) arrive, and their bytes.
//
// The join probe sees only the replicated-state chunks (FUN_146af2340). Every typed thing on the wire
// goes through the type reference reader FUN_1461acfe0 (RVA 0x61acfe0): a prefix varint typeIndex,
// then table[typeIndex] -> 16-byte uuid (docs/Network/alc-protocol-reference.md 1.3). Hooking it gives
// the census of every type read, and for a watch list the bytes that follow the reference, which is
// where a message body starts. Read-only.
const mod = Process.findModuleByName("NewWorld.exe") ||
    Process.enumerateModules().find(m => m.name.toLowerCase().indexOf("newworld") >= 0);
if (mod === null) throw new Error("NewWorld.exe module not found");
const BASE = mod.base;
const TYPE_REF = 0x61acfe0, VARINT = 0x87b5c0;
// typeIndex -> label (community catalog, capture-triage.html); replicated states are excluded on purpose
const WATCH = {
    2071: "DamageReceiver_OnDamageDealt", 3601: "Vitals_OnDamage", 2832: "ActionList_PlayHitScanEffects",
    1924: "DamageReceiver_DisplayImmuneText", 2218: "DamageReceiver_HandleMeleeDamage", 3031: "MomentaryOffense_OnDamageDealt",
    327: "ProjectileSpawner_OnServerSpawnAuthoritativeProjectile", 2900: "ProjectileSpawner_OnServerSpawn",
    5322: "SlayerScript_SendEntityEvent", 349: "PingMsg", 335: "TimeSynchMsg", 6484: "BaseGameChatMessage",
};
const KNOWN_STATES = new Set([11, 15, 10, 13, 16, 100, 129, 185, 899, 1525, 1528, 1652, 2187, 2267, 2850, 2912, 2930, 2932,
    3139, 3147, 3152, 3183, 3362, 3663, 3752, 3935, 4176, 4236, 4297, 5620, 6234]);
const census = {};
const buf = [];
let timer = null, armed = false, reads = 0;
const perThread = {};

function flush() {
    if (buf.length) send({ type: "rmi_samples", count: buf.length, items: buf.splice(0, buf.length) });
}
function hex(u8) { return Array.from(u8).map(b => b.toString(16).padStart(2, "0")).join(""); }

function arm() {
    if (armed) return "already-armed";
    armed = true;
    // the varint primitive writes the value behind args[2]; keep it per thread for the type-ref hook
    Interceptor.attach(BASE.add(VARINT), {
        onEnter(args) { this.out = args[2]; this.ctx = args[3]; },
        onLeave() {
            if (this.returnAddress.sub(BASE).toInt32() !== 0x61ad00f) return;   // the call inside FUN_1461acfe0
            try { perThread[this.threadId] = [this.out.readU32(), this.ctx]; } catch (e) { }
        }
    });
    Interceptor.attach(BASE.add(TYPE_REF), {
        onEnter(args) { this.ctx = args[2]; },
        onLeave() {
            reads++;
            const seen = perThread[this.threadId];
            if (!seen) return;
            const typeIndex = seen[0];
            census[typeIndex] = (census[typeIndex] || 0) + 1;
            if (KNOWN_STATES.has(typeIndex) || buf.length > 4000) return;
            let after = "";
            try {
                const cursor = this.ctx.add(0x10).readPointer(), end = this.ctx.add(0x08).readPointer();
                const n = Math.min(96, end.sub(cursor).toInt32());
                if (n > 0) after = hex(new Uint8Array(cursor.readByteArray(n)));
            } catch (e) { }
            buf.push([Date.now(), typeIndex, WATCH[typeIndex] || "", after]);
            if (buf.length >= 200) flush();
        }
    });
    timer = setInterval(flush, 500);
    return "armed";
}
rpc.exports = {
    install: function () { return arm(); },
    stop: function () {
        if (timer) clearInterval(timer);
        flush();
        send({ type: "rmi_census", items: Object.entries(census).map(([k, v]) => [Number(k), v]).sort((a, b) => b[1] - a[1]) });
        return "stopped reads=" + reads + " types=" + Object.keys(census).length;
    },
    total: function () { return reads; },
};
