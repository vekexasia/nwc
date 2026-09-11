#!/usr/bin/env python3
"""Live view during a capture: tail the probe log, decode, serve it on a local page.

    # 1. capture with the live probe (one probe, three kinds of samples)
    .venv-capture/bin/python Tools/nw_capture/experimental/nw_capture_probe.py \
        --probe "$PWD/Tools/nw_capture/experimental/nw_live_probe.js" --seconds 60 --label live

    # 2. while it runs, follow that log
    .venv-capture/bin/python Tools/nw_capture/experimental/nw_live.py \
        --log Tools/nw_capture/logs/<run>_live.log --port 8765
    # then open http://127.0.0.1:8765/

What it shows: world position per object (ALC worldPosAbs), health and mana per Vitals object, and the
player names from PlayerComponent. It does **not** know which object is you: the three states are
different objects with no common key yet, so the page lets you pick the object once and remembers it.
The decoders are the same ones used offline; this only adds the tailing.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "offline"))
from decode_vitals import parse_members  # noqa: E402  the shared, verified payload model

HERE_PAGE = HERE / "nw_live.html"


def decode_abs(payload_hex: str):
    """worldPosAbs: two big-endian float32 then a quantised u16 elevation in [-100, 1000]."""
    raw = bytes.fromhex(payload_hex)
    if len(raw) < 10:
        return None
    x, y, elevation = struct.unpack(">ffH", raw[:10])
    if not (-1e6 < x < 1e6 and -1e6 < y < 1e6):
        return None
    # The u16 is the quantised elevation as it comes off the wire: the affine mapping back to world
    # units is not established, so it is reported raw and named that way.
    return {"x": round(x, 2), "y": round(y, 2), "elev_raw": elevation}


class LiveState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.objects: dict[str, dict] = {}
        self.counters = {"position": 0, "health": 0, "mana": 0, "player": 0, "lines": 0, "skipped": 0}
        self.started = time.time()
        self.last_line_at: float | None = None

    def _slot(self, key: str) -> dict:
        return self.objects.setdefault(key, {"object": key})

    def position(self, key: str, position: dict) -> None:
        with self.lock:
            self._slot(key).update({"position": position, "position_at": time.time()})
            self.counters["position"] += 1

    def vitals(self, key: str, decoded: dict) -> None:
        with self.lock:
            slot = self._slot(key)
            slot["vitals_at"] = time.time()
            if "health" in decoded:
                slot["health"] = round(decoded["health"], 1)
                self.counters["health"] += 1
            if "mana" in decoded:
                slot["mana"] = round(decoded["mana"], 2)
                self.counters["mana"] += 1

    def player(self, key: str, name: str, character_id: str) -> None:
        with self.lock:
            slot = self._slot(key)
            slot["name"] = name
            slot["character_id"] = character_id
            self.counters["player"] += 1

    def skip(self) -> None:
        with self.lock:
            self.counters["skipped"] += 1

    def tick(self) -> None:
        with self.lock:
            self.counters["lines"] += 1
            self.last_line_at = time.time()

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "now": time.time(),
                "uptime_s": round(time.time() - self.started, 1),
                "last_line_age_s": None if self.last_line_at is None else round(time.time() - self.last_line_at, 2),
                "counters": dict(self.counters),
                "objects": {k: v for k, v in sorted(self.objects.items())},
            }


def apply_line(line: str, state: LiveState) -> None:
    """One JSONL line from a probe log. Unknown shapes are counted, never guessed at."""
    try:
        entry = json.loads(line)
    except Exception:
        state.skip()
        return
    kind = entry.get("type")
    items = entry.get("items") or []
    if kind == "pos_samples":
        for item in items:
            if len(item) < 4:
                continue
            ts, tag, key, payload_hex = item[0], item[1], item[2], item[3]
            if tag != "ABS":
                continue
            position = decode_abs(payload_hex)
            if position is None:
                state.skip()
            else:
                state.position(key, position)
    elif kind == "vitals_samples":
        for item in items:
            if len(item) < 3:
                continue
            decoded = parse_members(bytes.fromhex(item[2]))
            if decoded:
                state.vitals(item[1], decoded)
            else:
                state.skip()
    elif kind == "player_samples":
        for item in items:
            if len(item) < 4:
                continue
            state.player(item[1], item[2], item[3])
    elif kind == "state_calls":       # the older probes log this shape; accept them too
        for item in items:
            if len(item) < 5 or not item[4]:
                continue
            ts, name, _consumed, key, payload_hex = item[0], item[1], item[2], item[3], item[4]
            if name == "CONTROL-worldPosAbs-reader":
                position = decode_abs(payload_hex)
                if position is not None:
                    state.position(key, position)
            elif name == "Vitals-stage-90-mask":
                decoded = parse_members(bytes.fromhex(payload_hex))
                if decoded:
                    state.vitals(key, decoded)
    else:
        state.skip()
    state.tick()


def newest_log(directory: Path) -> Path | None:
    """The most recently modified .log in a directory, so a new capture is picked up on its own."""
    logs = sorted(directory.glob("*.log"), key=lambda p: p.stat().st_mtime if p.exists() else 0)
    return logs[-1] if logs else None


def tail(path: Path, state: LiveState, stop: threading.Event, poll: float = 0.2) -> None:
    """Follow an append-only JSONL log from a byte offset, keeping partial lines for the next pass.

    ``path`` may be a directory: then the newest ``*.log`` in it is followed, and a newer file
    replaces it, so one server can watch capture after capture.
    """
    offset = 0
    pending = b""
    if path.is_dir():
        path = newest_log(path) or path
        print(f"following the newest log in the directory: {path}")
    while not stop.is_set():
        if path.is_dir():
            candidate = newest_log(path)
            if candidate is not None and candidate != path:
                print(f"new capture: {candidate}")
                path, offset, pending = candidate, 0, b""
        try:
            size = path.stat().st_size
        except FileNotFoundError:
            time.sleep(poll)
            continue
        if size < offset:            # a new capture replaced the file
            offset, pending = 0, b""
        if size > offset:
            with open(path, "rb") as handle:
                handle.seek(offset)
                chunk = handle.read()
            offset += len(chunk)
            chunk = pending + chunk
            lines = chunk.split(b"\n")
            pending = lines.pop() if lines and not chunk.endswith(b"\n") else b""
            for raw in lines:
                if raw.strip():
                    apply_line(raw.decode("utf-8", "replace"), state)
        time.sleep(poll)


def make_handler(state: LiveState):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):    # quiet
            pass

        def do_GET(self):
            if self.path.startswith("/state"):
                body = json.dumps(state.snapshot()).encode()
                ctype = "application/json"
            elif self.path in ("/", "/index.html"):
                body = HERE_PAGE.read_bytes()
                ctype = "text/html; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    return Handler


def self_check() -> int:
    """The tailer must follow an appended log and must not consume a half-written line."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "synthetic.log"
        state = LiveState()
        log.write_text("")
        stop = threading.Event()
        thread = threading.Thread(target=tail, args=(log, state, stop), kwargs={"poll": 0.05}, daemon=True)
        thread.start()
        with open(log, "a") as handle:
            handle.write(json.dumps({"type": "pos_samples", "items": [[1, "ABS", "0xabc",
                struct.pack(">ffH", 8786.66, 3003.97, 58).hex()]]}) + "\n")
            handle.write(json.dumps({"type": "vitals_samples", "items": [[2, "0xabc",
                "0101461b88f3"]]}) + "\n")
            handle.write(json.dumps({"type": "player_samples", "items": [[3, "0xabc", "stormvind", "682b"]]}) + "\n")
        time.sleep(0.3)
        snapshot = state.snapshot()
        slot = snapshot["objects"].get("0xabc")
        assert slot is not None, snapshot
        assert abs(slot["position"]["x"] - 8786.66) < 0.01, slot
        assert abs(slot["position"]["y"] - 3003.97) < 0.01, slot
        assert slot["position"]["elev_raw"] == 58, slot
        assert abs(slot["health"] - 9954.2) < 0.1, slot
        assert slot["name"] == "stormvind", slot
        # a half-written line must wait for its newline
        with open(log, "a") as handle:
            handle.write('{"type": "vitals_samples", "items": [[4, "0xabc", "020142803317"')
        time.sleep(0.3)
        assert "mana" not in state.snapshot()["objects"]["0xabc"], "partial line was consumed"
        with open(log, "a") as handle:
            handle.write(']]}\n')
        time.sleep(0.3)
        assert abs(state.snapshot()["objects"]["0xabc"]["mana"] - 64.1) < 0.1, state.snapshot()
        stop.set()
    print("self-check ok: tail, position, health, mana, name, and a partial line held back")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--log", type=Path, help="probe log to follow, or a directory of them")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--check", action="store_true", help="run the self-check and exit")
    args = parser.parse_args(argv)
    if args.check:
        return self_check()
    if not args.log:
        parser.error("--log or --check is required")
    state = LiveState()
    stop = threading.Event()
    threading.Thread(target=tail, args=(args.log, state, stop), daemon=True).start()
    server = ThreadingHTTPServer((args.host, args.port), make_handler(state))
    print(f"following {args.log}")
    print(f"open http://{args.host}:{args.port}/   (state: /state)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
