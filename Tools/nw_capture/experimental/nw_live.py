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
player names from PlayerComponent. With entity-keyed join samples, e1 is the player by default; otherwise
the page can identify the player by walking or by picking a table row.
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
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "offline"))
from decode_stamina import parse_stamina  # noqa: E402
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
        self.max_path = self.me_path.with_name("nw_live_max.json")
        try:
            self.maxima = json.loads(self.max_path.read_text())
        except Exception:
            self.maxima = {}
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

    @staticmethod
    def _is_entity_key(key: str) -> bool:
        return key.startswith("e") and key[1:].isdigit()

    def _join_default(self, key: str) -> None:
        if not self._is_entity_key(key) or self.me.get("method") in ("walk", "picked"):
            return
        if self.me.get("object") == "e1" and self.me.get("method") == "join-default":
            return
        self.me = {"object": "e1", "method": "join-default", "at": time.time()}
        self._save_me()

    def _slot(self, key: str) -> dict:
        self._join_default(key)
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
        if self._is_entity_key(calibrated):
            return                        # entity keys are stable: a quiet player is standing still, not gone
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

    def pick(self, key: str) -> dict:
        """Say who you are without walking: the entity key clicked in the table."""
        with self.lock:
            slot = self.objects.get(key)
            self.me = {"object": key, "method": "picked", "at": time.time(),
                       "name": slot.get("name") if slot else None}
            self._save_me()
            return dict(self.me)

    def reset(self) -> dict:
        """Forget every entity (a new game session reuses the keys); identity and maxima are kept."""
        with self.lock:
            dropped = len(self.objects)
            self.objects.clear()
            self.calibration = None
            return {"dropped": dropped}

    def pick_by_name(self, name: str) -> dict:
        """The same, by character name: the join attaches names to entities, so a name is enough."""
        with self.lock:
            for key, slot in self.objects.items():
                if (slot.get("name") or "").lower() == name.lower():
                    return self.pick(key)
            return {"error": f"no entity named {name!r} seen yet",
                    "seen": sorted(slot.get("name") for slot in self.objects.values() if slot.get("name"))}

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
                self._remember_max(key, slot, "health")
            if "mana" in decoded:
                slot["mana"] = round(decoded["mana"], 2)
                self.counters["mana"] += 1
                self._remember_max(key, slot, "mana")

    # ponytail: HealthMax is a Vitals member we have not decoded (members 7..12), so the bar's ceiling
    # is the highest value seen, kept across server restarts in a small file keyed by entity key.
    def _remember_max(self, key: str, slot: dict, what: str) -> None:
        field = what + "_max"
        best = max(slot.get(field) or 0.0, self.maxima.get(key, {}).get(field, 0.0), slot[what])
        if best != slot.get(field):
            slot[field] = best
            self.maxima.setdefault(key, {})[field] = best
            try:
                self.max_path.parent.mkdir(parents=True, exist_ok=True)
                self.max_path.write_text(json.dumps(self.maxima))
            except Exception:
                pass

    def stamina(self, key: str, decoded: dict) -> None:
        """StaminaComponentReplicatedState: the bar itself, about 60 Hz while it moves."""
        with self.lock:
            slot = self._slot(key)
            slot["stamina_at"] = time.time()
            if "stamina" in decoded:
                slot["stamina"] = round(decoded["stamina"], 1)
                self.counters["stamina"] = self.counters.get("stamina", 0) + 1
            if "stamina_max" in decoded:
                slot["stamina_max"] = decoded["stamina_max"]
            for name in ("winded_s", "regen_delay_s"):
                if name in decoded:
                    slot[name] = decoded[name]

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
        if self.me.get("method") in ("walk", "picked", "join-default"):
            return          # explicit or join identity must not be replaced by movement heuristics
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
    elif kind == "join_samples":      # only the stamina state; position, vitals and names have their own shapes
        for item in items:
            if len(item) < 7 or item[3] != 4297 or len(item[6]) != 2 * item[5]:
                continue
            decoded = parse_stamina(bytes.fromhex(item[6]))
            if decoded:
                state.stamina(f"e{item[1]}", decoded)
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
                # Keep session state: names arrive once and must survive log rotation.
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

        def _answer(self, answer: dict) -> None:
            body = json.dumps(answer, allow_nan=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_POST(self):
            if self.path.startswith("/pick"):
                query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                if query.get("name"):
                    self._answer(state.pick_by_name(query["name"][0]))
                elif query.get("key"):
                    self._answer(state.pick(query["key"][0]))
                else:
                    self._answer({"error": "pass key= or name="})
            elif self.path.startswith("/reset"):
                self._answer(state.reset())
            elif self.path.startswith("/calibrate"):
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

        # reset drops the entities and keeps who you are
        state13 = LiveState()
        state13.me_path = Path(tmp) / "me13.json"; state13.max_path = Path(tmp) / "max13.json"; state13.maxima = {}
        state13.player("e1", "Tester", "id"); state13.me = {"object": "e1", "method": "picked"}
        assert state13.reset() == {"dropped": 1} and not state13.objects and state13.me["object"] == "e1"

        # the bar ceiling is the highest value seen and survives a restart
        state11 = LiveState()
        state11.me_path = Path(tmp) / "me11.json"; state11.max_path = Path(tmp) / "max11.json"; state11.maxima = {}
        state11.vitals("e1", {"health": 10519.7}); state11.vitals("e1", {"health": 8071.0})
        assert state11.objects["e1"]["health_max"] == 10519.7, state11.objects["e1"]
        state12 = LiveState()
        state12.me_path = Path(tmp) / "me12.json"; state12.max_path = Path(tmp) / "max11.json"
        state12.maxima = json.loads(state12.max_path.read_text())
        state12.vitals("e1", {"health": 8000.0})
        assert state12.objects["e1"]["health_max"] == 10519.7, state12.objects["e1"]

        # the stamina state rides on join_samples (typeIndex 4297); other types there are ignored
        state10 = LiveState()
        state10.me_path = Path(tmp) / "me10.json"
        apply_line(json.dumps({"type": "join_samples", "items": [
            [1, 5, 16, 15, "0x0", 3, "010100"],
            [2, 5, 62, 4297, "0x0", 10, "0109425c00003f800000"]]}), state10)
        assert state10.objects["e5"]["stamina"] == 55.0 and state10.objects["e5"]["regen_delay_s"] == 1.0, state10.objects

        # entity keys use the verified join identity unless the user has chosen one
        state7 = LiveState()
        state7.me_path = Path(tmp) / "me7.json"
        state7.me = {"object": None, "method": None}
        state7.player("e158", "Where Arda", "682b")
        assert state7.me["object"] == "e1" and state7.me["method"] == "join-default", state7.me
        state7.pick("e158")
        state7.player("e1", "stormvind", "player")
        assert state7.me["object"] == "e158" and state7.me["method"] == "picked", state7.me
        state7.me = {"object": "e220", "method": "walk"}
        state7.player("e1", "stormvind", "player")
        assert state7.me["object"] == "e220" and state7.me["method"] == "walk", state7.me

        # rotation changes the file, not the session state: names and values remain available
        rotation_dir = Path(tmp) / "rotating"
        rotation_dir.mkdir()
        first = rotation_dir / "first.log"
        first.write_text("")
        state8 = LiveState()
        state8.me_path = Path(tmp) / "me8.json"
        state8.me = {"object": None, "method": None}
        stop8 = threading.Event()
        thread8 = threading.Thread(target=tail, args=(rotation_dir, state8, stop8),
                                    kwargs={"poll": 0.05}, daemon=True)
        thread8.start()
        try:
            with open(first, "a") as handle:
                handle.write(json.dumps({"type": "pos_samples", "items": [[1, "ABS", "e158",
                    struct.pack(">ffH", 8786.66, 3003.97, 58).hex()]]}) + "\n")
                handle.write(json.dumps({"type": "vitals_samples", "items": [[2, "e158",
                    "0101461b88f3"]]}) + "\n")
                handle.write(json.dumps({"type": "player_samples", "items": [[3, "e158",
                    "Where Arda", "682b"]]}) + "\n")
            deadline = time.time() + 2.0
            while state8.objects.get("e158", {}).get("name") != "Where Arda" and time.time() < deadline:
                time.sleep(0.05)
            first_snapshot = state8.snapshot()
            first_slot = first_snapshot["objects"]["e158"]
            assert first_slot["name"] == "Where Arda" and "health" in first_slot, first_snapshot
            second = rotation_dir / "second.log"
            second.write_text("")
            with open(second, "a") as handle:
                handle.write(json.dumps({"type": "pos_samples", "items": [[4, "ABS", "e1",
                    struct.pack(">ffH", 9000.0, 3000.0, 59).hex()]]}) + "\n")
            deadline = time.time() + 2.0
            while "e1" not in state8.objects and time.time() < deadline:
                time.sleep(0.05)
            rotated_snapshot = state8.snapshot()
            rotated_slot = rotated_snapshot["objects"].get("e158")
            assert rotated_slot and rotated_slot["name"] == "Where Arda", rotated_snapshot
            assert "health" in rotated_slot and "position" in rotated_slot, rotated_snapshot
        finally:
            stop8.set()
            thread8.join(1)

        # with an entity key nothing is handed over: standing still is not disappearing
        state9 = LiveState()
        state9.me_path = Path(tmp) / "me9.json"
        state9.me = {"object": "e1", "method": "join-default"}
        state9.objects["e1"] = {"object": "e1", "position": {"x": 1.0, "y": 1.0}, "position_at": time.time() - 60}
        state9.position("e77", {"x": 2.0, "y": 2.0, "elev_raw": 0})
        assert state9.me["object"] == "e1" and "followed_from" not in state9.me, state9.me

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
