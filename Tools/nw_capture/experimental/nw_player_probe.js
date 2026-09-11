// Read PlayerComponentReplicatedState fields from the live client.
// The state's builder (RVA 0x6711e90, called per create by its unmarshal before the three-stage
// deserialiser fills the object) gives the state pointer; the field offsets come from the
// registration calls in that builder. Read-only.
const mod = Process.findModuleByName("NewWorld.exe") ||
    Process.enumerateModules().find(m => m.name.toLowerCase().indexOf("newworld") >= 0);
if (mod === null) throw new Error("NewWorld.exe module not found");
const BASE = mod.base;
const BUILDER = 0x6711e90;
const FIELDS = {           // offsets from the registration calls in FUN_146711e90
    characterId: 0x7c0,
    characterName: 0x870,
    homeWorldId: 0x8f0,
    srcWorldId: 0x9a0,
    playerType: 0xc68,
    platformAccountId: 0xe58,
};
const buf = [];
let timer = null, calls = 0;
function read(obj) {
    const out = {};
    for (const [name, off] of Object.entries(FIELDS)) {
        try {
            out[name] = Array.from(new Uint8Array(obj.add(off).readByteArray(32)))
                .map(b => b.toString(16).padStart(2, "0")).join("");
        } catch (e) { out[name] = null; }
    }
    // the name itself sits 16 bytes into the field (the first qword is a type pointer)
    try {
        const raw = new Uint8Array(obj.add(FIELDS.characterName + 0x10).readByteArray(48));
        let text = "";
        for (const byte of raw) {
            if (byte === 0 || byte < 0x20 || byte > 0x7e) break;
            text += String.fromCharCode(byte);
        }
        out.characterNameAscii = text;
    } catch (e) {}
    return out;
}
function flush() { if (buf.length) send({ type: "player_states", count: buf.length, items: buf.splice(0, buf.length) }); }
Interceptor.attach(BASE.add(BUILDER), {
    onEnter(args) { this.obj = args[0]; },
    onLeave() {
        calls++;
        const obj = this.obj;
        if (obj === null || obj.isNull()) return;
        const pointer = obj.toString();
        try { buf.push([Date.now(), pointer, "on-leave", read(obj)]); } catch (e) {}
        setTimeout(function () {
            try { buf.push([Date.now(), pointer, "after-150ms", read(obj)]); } catch (e) {}
            flush();
        }, 150);
        if (buf.length >= 40) flush();
    }
});
rpc.exports = {
    install: function () { timer = setInterval(flush, 500); return "armed"; },
    stop: function () { if (timer) clearInterval(timer); flush(); return "stopped calls=" + calls; },
    total: function () { return calls; },
};
