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
import math
import os
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
    if not (math.isfinite(x) and math.isfinite(y)):
        return None
    if not (-1e6 < x < 1e6 and -1e6 < y < 1e6):
        return None
    # The u16 is the quantised elevation as it comes off the wire: the affine mapping back to world
    # units is not established, so it is reported raw and named that way.
    return {"x": round(x, 2), "y": round(y, 2), "elev_raw": elevation}


class LiveState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.objects: dict[str, dict] = {}
        self.me: dict = {"object": None, "method": None}

        self.history: dict[str, list[tuple[float, float, float]]] = {}
        self.auto_strikes: dict[str, int] = {}
        self.auto_debug: dict = {}
        self.last_auto = 0.0
        self.me_path = Path(os.environ.get("NW_LIVE_ME", "/tmp/nwc/nw_live_me.json"))
        if self.me_path.exists():
            try:
                loaded = json.loads(self.me_path.read_text())
                if loaded.get("object"):
                    self.me = loaded          # survives a server restart; the id holds while the game runs
            except Exception:
                pass
        self.calibration: dict | None = None   # {"until": ts, "started": ts, "moved": {key: distance}}
        self.counters = {"position": 0, "health": 0, "mana": 0, "player": 0, "lines": 0, "skipped": 0}
        self.started = time.time()
        self.last_line_at: float | None = None

    def _slot(self, key: str) -> dict:
        return self.objects.setdefault(key, {"object": key})

    def _save_me(self) -> None:
        try:
            self.me_path.parent.mkdir(parents=True, exist_ok=True)
            self.me_path.write_text(json.dumps(self.me))
        except Exception:
            pass

    def _follow(self, key: str, position: dict) -> None:
        """Hand the identification over when the state object is recreated.

        The game rebuilds these state objects, so the calibrated pointer goes stale while the entity
        stays. The identity fields we have are either per-record bookkeeping or readers shared by
        dozens of fields, so there is no stable id to key on: this follows the entity by continuity
        instead, and the page is told when it happens.
        """
        me = self.me
        calibrated = me.get("object")
        if not calibrated or key == calibrated:
            return
        last = self.objects.get(calibrated) or {}
        reference = last.get("position")
        if reference is None or (time.time() - (last.get("position_at") or 0)) < 15:
            return                        # the calibrated object is still talking: keep it
        # The candidate is talking right now (we are handling its position), and the object may well be
        # one we have seen before: the game reuses state objects, so "already seen" says nothing.
        distance = abs(position["x"] - reference["x"]) + abs(position["y"] - reference["y"])
        if distance > 25:
            return
        me["object"] = key
        me["followed_from"] = calibrated
        me["followed_at"] = time.time()
        me["follow_distance"] = round(distance, 1)
        self._save_me()

    def position(self, key: str, position: dict) -> None:
        if not all(math.isfinite(position.get(k, 0.0)) for k in ("x", "y")):
            return
        with self.lock:
            self._follow(key, position)
            if self.me.get("object") == key:
                self.me["at"] = time.time()
            now = time.time()
            history = self.history.setdefault(key, [])
            history.append((now, position["x"], position["y"]))
            while history and now - history[0][0] > 8.0:
                history.pop(0)
            previous = self._slot(key).get("position")
            self._slot(key).update({"position": position, "position_at": time.time()})
            self.counters["position"] += 1
            window = self.calibration
            if window is not None and previous is not None:
                step = abs(position["x"] - previous["x"]) + abs(position["y"] - previous["y"])
                if step < 500:      # a teleport or a bad read is not a step
                    window["moved"][key] = window["moved"].get(key, 0.0) + step

    def start_calibration(self, seconds: float = 3.0) -> None:   # manual override, kept for the page
        """Watch the next seconds of movement: the object that walks is the player."""
        with self.lock:
            self.calibration = {"started": time.time(), "until": time.time() + seconds, "moved": {}}

    def finish_calibration(self) -> dict:
        with self.lock:
            window = self.calibration
            self.calibration = None
            if window is None:
                return dict(self.me)
            moved = sorted(window["moved"].items(), key=lambda kv: -kv[1])
            if not moved or moved[0][1] < 3.0:
                return {"object": self.me.get("object"), "method": None,
                        "note": "no object moved more than 3 units: nothing identified"}
            best = moved[0][0]
            margin = moved[0][1] / moved[1][1] if len(moved) > 1 and moved[1][1] > 1e-6 else None
            self.me = {"object": best, "method": "walk", "distance": round(moved[0][1], 1),
                       "margin_over_next": None if margin is None else round(margin, 2),
                       "at": time.time()}
            self._save_me()
            return dict(self.me)

    def calibration_active(self) -> bool:
        with self.lock:
            return self.calibration is not None and time.time() < self.calibration["until"]

    def vitals(self, key: str, decoded: dict) -> None:
        with self.lock:
            slot = self._slot(key)
            slot["vitals_at"] = time.time()
            decoded = {k: v for k, v in decoded.items() if math.isfinite(v)}
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

    def _me_view(self) -> dict:
        """The identification plus whether it is still alive, so the page can say so."""
        me = dict(self.me)
        slot = self.objects.get(me.get("object") or "")
        latest = max(slot.get("position_at") or 0, me.get("at") or 0) if slot else (me.get("at") or 0)
        me["position_age_s"] = None if not latest else round(time.time() - latest, 1)
        me["stale"] = bool(me.get("object")) and (me["position_age_s"] is None or me["position_age_s"] > 45)
        return me

    HISTORY_WINDOW = 8.0          # seconds of movement the auto tracker looks at
    AUTO_EVERY = 2.0              # how often it re-evaluates
    AUTO_MIN_MOVE = 25.0          # in 8s a walking player covers tens of units; a wandering mob does not
    AUTO_MARGIN = 1.6             # ...and beat the next candidate by this much (mobs wander too)
    AUTO_CONFIRMATIONS = 2        # ...twice in a row, so one lucky window does not decide it
    AUTO_KEEP_FRACTION = 0.4      # if the current "me" still moves this much of the best, keep it

    def _auto_identify(self, now: float) -> None:
        """Pick the player without being told: the object that is walking is the one being walked.

        Scoped on purpose: this only ever decides *identity*, never the coordinates, and every decision
        is reported with its margin so a wrong pick is visible in the page instead of silent.
        """
        if self.me.get("method") == "walk":
            return          # you told it who you are: with entity keys that stays true, never override it
        if now - self.last_auto < self.AUTO_EVERY:
            return
        self.last_auto = now
        moved: dict[str, float] = {}
        for key, history in self.history.items():
            if len(history) < 2:
                continue
            displacement = max(
                abs(point[1] - history[0][1]) + abs(point[2] - history[0][2]) for point in history)
            if displacement >= self.AUTO_MIN_MOVE:
                moved[key] = displacement
        self.auto_debug = {
            "candidates": {key: round(value, 1) for key, value in sorted(
                moved.items(), key=lambda kv: -kv[1])[:4]},
            "window_s": self.HISTORY_WINDOW,
            "min_move": self.AUTO_MIN_MOVE,
            "margin_needed": self.AUTO_MARGIN,
            "strikes": {key: value for key, value in self.auto_strikes.items() if value},
        }
        if not moved:
            return
        best = max(moved, key=moved.get)
        best_distance = moved[best]
        runner_up = max((value for key, value in moved.items() if key != best), default=0.0)
        current = self.me.get("object")
        if current and moved.get(current, 0.0) >= self.AUTO_KEEP_FRACTION * best_distance:
            return                                  # the one we already follow is moving: keep it
        if runner_up > 0 and best_distance < self.AUTO_MARGIN * runner_up:
            self.auto_strikes[best] = 0             # ambiguous window: nothing decided
            return
        self.auto_strikes[best] = self.auto_strikes.get(best, 0) + 1
        for key in list(self.auto_strikes):
            if key != best:
                self.auto_strikes[key] = 0
        if self.auto_strikes[best] < self.AUTO_CONFIRMATIONS:
            return
        self.me = {"object": best, "method": "auto", "distance": round(best_distance, 1),
                   "margin_over_next": round(best_distance / runner_up, 2) if runner_up else None,
                   "at": now, "previous": current}
        self._save_me()

    def tick(self) -> None:
        with self.lock:
            self.counters["lines"] += 1
            self.last_line_at = time.time()

    def snapshot(self) -> dict:
        with self.lock:
            self._auto_identify(time.time())
            return {
                "now": time.time(),
                "uptime_s": round(time.time() - self.started, 1),
                "last_line_age_s": None if self.last_line_at is None else round(time.time() - self.last_line_at, 2),
                "counters": dict(self.counters),
                "me": self._me_view(),
                "auto": dict(self.auto_debug),
                # inside the lock already: calibration_active() would take it again
                "calibrating": self.calibration is not None and time.time() < self.calibration["until"],
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
    directory = path if path.is_dir() else None
    if directory is not None:
        path = newest_log(directory) or path
        print(f"following the newest log in {directory}: {path}", flush=True)
    while not stop.is_set():
        if directory is not None:
            candidate = newest_log(directory)
            if candidate is not None and candidate != path:
                print(f"new capture: {candidate}", flush=True)
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

        def do_POST(self):
            if self.path.startswith("/calibrate"):
                state.start_calibration(3.0)
                time.sleep(3.2)
                body = json.dumps(state.finish_calibration()).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_error(404)

        def do_GET(self):
            if self.path.startswith("/state"):
                # allow_nan=False: a non-finite number would make the browser's JSON.parse fail, which
                # is exactly what showed up as "cannot reach the server" in the page.
                body = json.dumps(state.snapshot(), allow_nan=False).encode()
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
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass   # the browser navigated away mid-request (clicking a link does this)

    return Handler


def check_page_script() -> str:
    """The page's inline script must parse. A stray redeclaration killed it silently once."""
    import re
    import shutil
    import subprocess as sp
    import tempfile

    html = HERE_PAGE.read_text()
    match = re.search(r"<script>(.*?)</script>", html, re.S)
    if match is None:
        return "the page has no inline script?"
    node = shutil.which("node")
    if node is None:
        return "node not found: page script not checked"
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as handle:
        handle.write(match.group(1))
        path = handle.name
    try:
        result = sp.run([node, "--check", path], capture_output=True, text=True)
        if result.returncode != 0:
            raise AssertionError("page script does not parse: " + result.stderr.strip().splitlines()[-1])
    finally:
        Path(path).unlink(missing_ok=True)
    return "page script parses"


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
        # calibration: the object that walks is the one that moved most, and the margin is reported
        state2 = LiveState()
        state2.me_path = Path(tmp) / "me.json"    # never overwrite the real identification
        state2.start_calibration(10.0)
        state2.position("0xwalker", {"x": 100.0, "y": 100.0, "elev_raw": 1})
        state2.position("0xidle", {"x": 500.0, "y": 500.0, "elev_raw": 1})
        for step in range(1, 7):
            state2.position("0xwalker", {"x": 100.0 + 5 * step, "y": 100.0, "elev_raw": 1})
            state2.position("0xidle", {"x": 500.0 + 0.2 * step, "y": 500.0, "elev_raw": 1})
        picked = state2.finish_calibration()
        assert picked["object"] == "0xwalker", picked
        assert picked["distance"] == 30.0, picked
        assert picked["margin_over_next"] and picked["margin_over_next"] > 10, picked
        # a NaN must never reach the JSON: the browser cannot parse it
        state3 = LiveState()
        state3.me_path = Path(tmp) / "me3.json"
        nan_payload = struct.pack(">f", float("nan")).hex()
        state3.vitals("0xnan", {"health": float("nan"), "mana": 12.5})
        state3.position("0xnan", {"x": float("inf"), "y": 1.0, "elev_raw": 1})
        blob = json.dumps(state3.snapshot(), allow_nan=False)      # must not raise
        assert "NaN" not in blob and "Infinity" not in blob, blob
        assert state3.snapshot()["objects"]["0xnan"].get("mana") == 12.5, state3.snapshot()

        # continuity: when the calibrated object goes quiet and another shows up where it was, take over
        state4 = LiveState()
        state4.me_path = Path(tmp) / "me4.json"
        state4.me = {"object": "0xold", "method": "walk", "at": time.time() - 100}
        state4.position("0xold", {"x": 100.0, "y": 100.0, "elev_raw": 1})
        state4.objects["0xold"]["position_at"] = time.time() - 60
        state4.position("0xnew", {"x": 103.0, "y": 101.0, "elev_raw": 1})
        assert state4.me["object"] == "0xnew", state4.me
        assert state4.me["followed_from"] == "0xold", state4.me
        # ...but not to something far away
        state5 = LiveState()
        state5.me_path = Path(tmp) / "me5.json"
        state5.me = {"object": "0xold", "method": "walk", "at": time.time() - 100}
        state5.position("0xold", {"x": 100.0, "y": 100.0, "elev_raw": 1})
        state5.objects["0xold"]["position_at"] = time.time() - 60
        state5.position("0xfar", {"x": 500.0, "y": 500.0, "elev_raw": 1})
        assert state5.me["object"] == "0xold", state5.me

        # auto identification: no button, the walker is adopted after two confirmations
        state6 = LiveState()
        state6.me_path = Path(tmp) / "me6.json"
        state6.me = {"object": None, "method": None}   # the constructor loads the real one
        state6.last_auto = 0.0
        base = time.time() - 6
        for step in range(6):
            state6.position("0xwalker", {"x": 100.0 + 10 * step, "y": 100.0, "elev_raw": 1})
            state6.position("0xstill", {"x": 900.0, "y": 900.0, "elev_raw": 1})
        state6.history["0xwalker"] = [(base + i, 100.0 + 10 * i, 100.0) for i in range(6)]
        state6._auto_identify(time.time())
        assert state6.me.get("object") is None, state6.me          # one window is not enough
        state6._auto_identify(time.time() + LiveState.AUTO_EVERY)
        assert state6.me["object"] == "0xwalker", state6.me
        assert state6.me["method"] == "auto" and state6.me["margin_over_next"] is None, state6.me
        # ...and it does not switch away while the tracked object is still the one walking
        state6.history["0xother"] = [(base + i, 500.0 + i, 500.0) for i in range(6)]
        state6._auto_identify(time.time() + 2 * LiveState.AUTO_EVERY)
        assert state6.me["object"] == "0xwalker", state6.me

        # when nothing moves the previous identification is kept, and the run says so
        state2.start_calibration(10.0)
        state2.position("0xidle", {"x": 500.0, "y": 500.0, "elev_raw": 1})
        quiet = state2.finish_calibration()
        assert quiet["object"] == "0xwalker" and quiet["note"], quiet
        stop.set()
    print("self-check ok: tail, position, health, mana, name, partial line, walk calibration, "
          "JSON strictness, and " + check_page_script())
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
