// nw_watch_addr.js - poll a few known addresses and log every value change (read-only).
// Used to follow the live health value while a fight is happening.
rpc.exports = {};

const ADDRESSES = ["0x15c6a810", "0x15c6a4f0", "0x15c6a680", "0x15c6a4e0"];
const INTERVAL_MS = 200;
const WATCH_S = 300;

let timer = null;
const last = {};

function readAt(addr) {
    try {
        return addr.readU32();
    } catch (e) {
        return null;
    }
}

function tick() {
    for (const text of ADDRESSES) {
        const addr = ptr(text);
        const value = readAt(addr);
        if (value === null) continue;
        if (last[text] === undefined) { last[text] = value; send(JSON.stringify({ t: Date.now(), addr: text, value: value, first: true })); continue; }
        if (value !== last[text]) {
            send(JSON.stringify({ t: Date.now(), addr: text, from: last[text], to: value, delta: value - last[text] }));
            last[text] = value;
        }
    }
}

rpc.exports = {
    install: function () {
        if (timer === null) timer = setInterval(tick, INTERVAL_MS);
        setTimeout(tick, 300);
        return true;
    },
    stop: function () {
        if (timer !== null) { clearInterval(timer); timer = null; }
        return "stopped watched=" + Object.keys(last).length;
    },
    total: function () { return Object.keys(last).length; },
};
