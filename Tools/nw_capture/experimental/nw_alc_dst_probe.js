// Runtime ALCReplicatedState reader probe.
//
// The mask reader has the same four-argument shape as the other prefix reader:
// (status, status, output, reader_context).  A field reader is
// (descriptor, reader_context).  Cursors are sampled before and after the
// call, so the exact consumed bytes can be joined to the plaintext ledger.
// Read-only: no game memory is written.
const mod = Process.findModuleByName("NewWorld.exe") ||
    Process.enumerateModules().find(m => m.name.toLowerCase().indexOf("newworld") >= 0);
if (mod === null) throw new Error("NewWorld.exe module not found");
const BASE = mod.base;

const FIELD_READERS = [
    [0x2a433d0, "worldPosAbs"],
    [0x2a43330, "worldPosRel"],
    [0x2a42d40, "u8"],
    [0x2a42da0, "u8High"],
    [0x2a42e10, "u16"],
    [0x2a42e60, "prefixVarint"],
    [0x2a42eb0, "u8Float"],
    [0x2a42f30, "u32"],
    [0x2a42f80, "halfFloat"],
    [0x2a42fd0, "bytes12"],
    [0x2a43020, "boolOptional"],
    [0x2a43140, "bytes33"],
    [0x2a43230, "bytes177"],
    [0x2a434b0, "lookDirQuaternion"],
    [0x2a43380, "rotationQuaternion"],
    [0x2a43500, "u64"],
    [0x279e210, "u8State"],
    [0x17b3c60, "u8GridAccessibility"],
];
const MAX_CONSUMED_BYTES = 256;
const MAX_PENDING_EVENTS = 8192;
const FLUSH_BATCH_SIZE = 256;

const pending = [];
let armed = false;
let timer = null;
let maskCalls = 0;
let fieldCalls = 0;
let loggedMasks = 0;
let loggedFields = 0;

function hexBytes(address, size) {
    if (size === 0) return "";
    return Array.from(new Uint8Array(address.readByteArray(size)))
        .map(b => b.toString(16).padStart(2, "0")).join("");
}

function enqueue(event) {
    if (pending.length >= MAX_PENDING_EVENTS) return;
    pending.push(event);
    if (pending.length >= FLUSH_BATCH_SIZE) flush();
}

function flush() {
    if (pending.length === 0) return;
    send({ type: "alc_reader_trace", count: pending.length, items: pending.splice(0, pending.length) });
}

function cursorOf(context) {
    return context.add(0x10).readPointer();
}

function commonEvent(kind, name, caller, before, after, consumed, raw) {
    return {
        ts_ms: Date.now(),
        kind: kind,
        reader: name,
        caller_rva: caller,
        cursor_in: before.toString(),
        cursor_out: after.toString(),
        consumed: consumed,
        raw: raw,
    };
}

function hookMaskReader() {
    Interceptor.attach(BASE.add(0x87b770), {
        onEnter(args) {
            maskCalls++;
            this.readerContext = args[3];
            this.outputPtr = args[2];
            try {
                this.cursorIn = cursorOf(this.readerContext);
            } catch (e) {
                this.cursorIn = null;
            }
        },
        onLeave() {
            if (this.cursorIn === null) return;
            try {
                const cursorOut = cursorOf(this.readerContext);
                const consumed = cursorOut.sub(this.cursorIn).toInt32();
                if (consumed < 0 || consumed > MAX_CONSUMED_BYTES) return;
                const raw = hexBytes(this.cursorIn, consumed);
                const event = commonEvent(
                    "mask", "fieldMask", this.returnAddress.sub(BASE).toString(),
                    this.cursorIn, cursorOut, consumed, raw);
                event.value = this.outputPtr.readU64().toString();
                enqueue(event);
                loggedMasks++;
            } catch (e) {
                // A failed read is not useful for cursor correlation.
            }
        },
    });
}

function hookFieldReader(address, name) {
    Interceptor.attach(BASE.add(address), {
        onEnter(args) {
            fieldCalls++;
            this.dstPtr = args[0];
            this.readerContext = args[1];
            try {
                this.cursorIn = cursorOf(this.readerContext);
            } catch (e) {
                this.cursorIn = null;
            }
        },
        onLeave() {
            if (this.cursorIn === null) return;
            try {
                const cursorOut = cursorOf(this.readerContext);
                const consumed = cursorOut.sub(this.cursorIn).toInt32();
                if (consumed < 0 || consumed > MAX_CONSUMED_BYTES) return;
                const raw = hexBytes(this.cursorIn, consumed);
                const event = commonEvent(
                    "field", name, this.returnAddress.sub(BASE).toString(),
                    this.cursorIn, cursorOut, consumed, raw);
                event.dst = this.dstPtr === null || this.dstPtr === undefined
                    ? null : this.dstPtr.toString();
                enqueue(event);
                loggedFields++;
            } catch (e) {
                // The reader may reject an incomplete buffer; keep the probe alive.
            }
        },
    });
}

function arm() {
    if (armed) return "already-armed";
    armed = true;
    hookMaskReader();
    for (const [address, name] of FIELD_READERS) hookFieldReader(address, name);
    timer = setInterval(flush, 1000);
    return "armed readers=" + FIELD_READERS.length;
}

rpc.exports = {
    install: function () { return arm(); },
    stop: function () {
        if (timer !== null) clearInterval(timer);
        flush();
        return "stopped mask_calls=" + maskCalls +
            " logged_masks=" + loggedMasks +
            " field_calls=" + fieldCalls +
            " logged_fields=" + loggedFields;
    },
    total: function () { return maskCalls + fieldCalls; },
};
